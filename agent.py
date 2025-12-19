"""Planner-Executor-Evaluator with multi-turn clarification and simple session integration.
This version supports: asking for missing profile fields, handling numeric responses,
and asking for ASR re-record when confidence is low.
"""
from typing import Dict, Any, List, Optional
import re

from src.tools.eligibility_engine import check_eligibility
from src.tools.mock_api import submit_application
from src.tools.retrieval import search_schemes, get_scheme_by_id
from src.memory.store import get_session, set_waiting, add_history


def parse_confirmation(transcript: str) -> bool | None:
    """Simple yes/no parser for Telugu (and English fallbacks).
    Returns True for yes, False for no, or None if unclear.
    """
    if not transcript:
        return None
    t = transcript.strip().lower()
    yes_tokens = ["అవును", "అవు", "సరే", "yes"]
    no_tokens = ["లేదు", "కాదు", "no"]

    found_yes = any(tok in t for tok in yes_tokens)
    found_no = any(tok in t for tok in no_tokens)
    if found_yes and not found_no:
        return True
    if found_no and not found_yes:
        return False
    return None


class Planner:
    def plan(self, session: Dict[str, Any], transcript: str, confidence: float) -> List[Dict[str, Any]]:
        """Decide next step based on session state, transcript and ASR confidence."""
        steps: List[Dict[str, Any]] = []
        # If ASR confidence low, instruct to clarify
        if confidence < 0.6:
            steps.append({"step": "clarify_asr"})
            return steps

        # If waiting for a specific field, route to the appropriate handler
        waiting = session.get("waiting_for")
        if waiting:
            # allow asking for scheme details even when waiting for confirmation
            if waiting == "confirmation":
                # if the user asks for details about a scheme, plan describe_scheme
                if any(k in (transcript or "").lower() for k in ["వివర", "వివరాలు", "details", "more", "about"]):
                    steps.append({"step": "describe_scheme", "query": transcript})
                    return steps
                steps.append({"step": "confirm"})
                return steps
            steps.append({"step": "fill_field", "field": waiting})
            return steps

        # If we have insufficient profile data, start asking
        profile = session.get("profile", {})
        missing = [f for f in ["age", "income"] if profile.get(f) is None]
        if missing:
            steps.append({"step": "ask_field", "field": missing[0]})
            return steps

        # Otherwise check eligibility
        steps.append({"step": "check_eligibility"})
        return steps


class Executor:
    def execute(self, step: Dict[str, Any], session_id: str, transcript: str) -> Dict[str, Any]:
        name = step.get("step")
        session = get_session(session_id)
        if not session:
            return {"status": "error", "error": "no_session"}

        if name == "clarify_asr":
            set_waiting(session_id, None)
            # Telugu clarification prompt
            reply = "క్షమించండి, నేను స్పష్టంగా వినలేకపోయాను. దయచేసి మళ్లీ రికార్డ్ చేయండి."
            add_history(session_id, "assistant", reply)
            return {"status": "clarify", "reply": reply}

        if name == "ask_field":
            field = step.get("field")
            if field == "age":
                reply = "దయచేసి మీ వయస్సును చెప్పండి."  # "Please tell me your age"
                set_waiting(session_id, "age")
            elif field == "income":
                reply = "దయచేసి మీ వార్షిక ఆదాయాన్ని (ఒక సంఖ్యలో) చెప్పండి."  # "Please state your annual income as a number"
                set_waiting(session_id, "income")
            else:
                reply = "సమాధానం తెలియదు."
            add_history(session_id, "assistant", reply)
            return {"status": "ask", "reply": reply}

        if name == "fill_field":
            field = step.get("field")
            filled = self._parse_and_set_field(session_id, field, transcript)
            if not filled:
                # couldn't parse, ask again
                reply = f"క్షమించండి, మీ {field} గురించి స్పష్టంగా చెప్పగలరా?"
                set_waiting(session_id, field)
                add_history(session_id, "assistant", reply)
                return {"status": "ask", "reply": reply}
            else:
                set_waiting(session_id, None)
                # continue planning next step
                return {"status": "filled", "field": field}

        if name == "check_eligibility":
            profile = session.get("profile", {})
            eligible = check_eligibility(profile)
            session["last_eligibility"] = eligible
            if eligible:
                # present first few results
                names = ", ".join([s["name"] for s in eligible])
                reply = f"మీకు ఈ పథకాలకు అర్హత ఉంది: {names}. మీరు దరఖాస్తు చేయాలనుకుంటున్నారా? (అవును/లేదు)"
                set_waiting(session_id, "confirmation")
            else:
                reply = "క్షమించండి, ప్రస్తుత సమాచారం ప్రకారం మీకు తెలియజేసేందుకు అనుకూలమైన పథకం కనిపించలేదు."
                set_waiting(session_id, None)
            add_history(session_id, "assistant", reply)
            return {"status": "eligible_check", "reply": reply, "eligible": eligible}

        if name == "describe_scheme":
            # try to find scheme by name/id from the query or from last_eligibility
            query = step.get("query") or transcript or ""
            session = get_session(session_id)
            last = session.get("last_eligibility") or []

            # search among last eligible schemes first
            hits = []
            for s in last:
                if s.get("name", "").lower() in (query or "").lower() or s.get("id", "").lower() in (query or "").lower():
                    hits.append(s)
            if not hits:
                # fallback to global search
                hits = search_schemes(query)

            if not hits:
                reply = "క్షమించండి, ఆ పథకం గురించి వివరాలు నాకు లభించలేదు. మీరు మరొకటి అడగాలనుకుంటున్నారా?"
                set_waiting(session_id, "confirmation")
                add_history(session_id, "assistant", reply)
                return {"status": "no_details", "reply": reply}

            # return description of first hit
            first = hits[0]
            doc = get_scheme_by_id(first.get("id"))
            reply = f"{doc.get('name')}: {doc.get('description')}"
            # keep waiting for confirmation (user must still accept/decline)
            set_waiting(session_id, "confirmation")
            add_history(session_id, "assistant", reply)
            return {"status": "describe", "reply": reply}

        if name == "confirm":
            # parse yes/no from the user's transcript
            parsed = parse_confirmation(transcript)
            if parsed is True:
                profile = session.get("profile", {})
                res = submit_application({"profile": profile})
                app_id = res.get("application_id")
                reply = f"మీ దరఖాస్తు విజయవంతంగా సమర్పించబడింది. దరఖాస్తు ID: {app_id}"
                add_history(session_id, "assistant", reply)
                set_waiting(session_id, None)
                return {"status": "submitted", "reply": reply, "application_id": app_id}
            elif parsed is False:
                reply = "సరే, నేను దరఖాస్తును నిలిపివెతున్నాను. మరింత సహాయం కావాలనుకుంటే చెప్పండి."
                add_history(session_id, "assistant", reply)
                set_waiting(session_id, None)
                return {"status": "declined", "reply": reply}
            else:
                # unclear, ask explicitly
                reply = "దయచేసి అవును లేదా కాదు అని చెప్పగలరా? (అవును/లేదు)"
                set_waiting(session_id, "confirmation")
                add_history(session_id, "assistant", reply)
                return {"status": "confirm_ask", "reply": reply}

        if name == "submit_application":
            profile = session.get("profile", {})
            res = submit_application({"profile": profile})
            reply = f"Your application has been submitted. ID: {res.get('application_id')}"
            add_history(session_id, "assistant", reply)
            set_waiting(session_id, None)
            return {"status": "submitted", "reply": reply}
        return {"status": "unknown_step"}

    def _parse_and_set_field(self, session_id: str, field: str, transcript: str) -> bool:
        session = get_session(session_id)
        if field == "age":
            m = re.search(r"(\d{1,3})", transcript)
            if m:
                session["profile"]["age"] = int(m.group(1))
                return True
            return False
        if field == "income":
            m = re.search(r"(\d{3,})", transcript.replace(",", ""))
            if m:
                session["profile"]["income"] = int(m.group(1))
                return True
            return False
        return False


class Evaluator:
    def evaluate(self, exec_out: Dict[str, Any]) -> Dict[str, Any]:
        # For demo, rely on executor outputs; could add hallucination checks.
        return exec_out


class Agent:
    """Facade to manage a session-based, multi-turn agentic loop."""

    def __init__(self):
        self.planner = Planner()
        self.executor = Executor()
        self.evaluator = Evaluator()

    def process_input(self, session_id: str, transcript: str, confidence: float, language: str = "te") -> Dict[str, Any]:
        session = get_session(session_id)
        if not session:
            return {"status": "error", "error": "session_not_found"}

        # record user utterance
        add_history(session_id, "user", transcript)

        response: Optional[Dict[str, Any]] = None
        # Allow multiple micro-steps in one call (e.g., fill age -> ask income)
        for _ in range(5):
            plan = self.planner.plan(session, transcript, confidence)
            if not plan:
                break
            any_action = False
            for step in plan:
                any_action = True
                exec_out = self.executor.execute(step, session_id, transcript)
                eval_out = self.evaluator.evaluate(exec_out)
                response = eval_out
                # If executor returned a reply, return early
                if exec_out.get("reply"):
                    out = {
                        "status": eval_out.get("status"),
                        "reply": eval_out.get("reply"),
                        "eligible": eval_out.get("eligible"),
                    }
                    if exec_out.get("application_id"):
                        out["application_id"] = exec_out.get("application_id")
                    return out
                # If we filled a field, continue the outer loop to plan next step
                if eval_out.get("status") == "filled":
                    # refresh session and re-plan
                    session = get_session(session_id)
                    break
            if not any_action:
                break

        # Fallback return
        out = {
            "status": response.get("status") if response else "no_action",
            "reply": response.get("reply") if response else "",
            "eligible": response.get("eligible") if response else None,
        }
        if response and response.get("application_id"):
            out["application_id"] = response.get("application_id")
        return out


# convenience
agent = Agent()
