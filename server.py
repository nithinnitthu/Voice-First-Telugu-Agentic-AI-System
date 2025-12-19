"""A minimal FastAPI server to demo ASR -> Agent -> TTS flow with confidence and provider options."""
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
ASR_PROVIDER = os.getenv("ASR_PROVIDER", "local")  # 'local' or provider name
ASR_CONFIDENCE_THRESHOLD = float(os.getenv("ASR_CONFIDENCE_THRESHOLD", "0.6"))

from src.asr.asr import transcribe_file
from src.tts.tts import text_to_speech
from src.tools.retrieval import DOCUMENTS, get_scheme_by_id

app = FastAPI()
TMP_DIR = Path("tmp")
TMP_DIR.mkdir(exist_ok=True)
WEB_DIR = Path(__file__).resolve().parent / "web"
WEB_DIR.mkdir(exist_ok=True)


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    path = TMP_DIR / file.filename
    with open(path, "wb") as f:
        f.write(await file.read())
    try:
        use_cloud = ASR_PROVIDER != "local"
        result = transcribe_file(str(path), language="te", use_cloud=use_cloud)
        text = result.get("text", "")
        confidence = result.get("confidence", 0.0)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    low_confidence = confidence < ASR_CONFIDENCE_THRESHOLD
    resp = {"text": text, "confidence": confidence, "low_confidence": low_confidence}
    if low_confidence:
        # Telugu: "Sorry, I couldn't understand clearly. Could you please repeat?"
        resp["clarify_prompt"] = "క్షమించండి, నేను మీరు చెప్పినది స్పష్టంగా గ్రహించలేకపోయాను. దయచేసి మళ్లీ చెప్పగలరా?"
    return resp


@app.post("/agent")
async def agent_endpoint(payload: dict):
    """Main agent endpoint.
    Accepts: { "session_id"?: str, "transcript": str, "confidence"?: float }
    If `session_id` is missing, a new one will be created and returned.
    """
    from src.memory.store import create_session, get_session
    from src.agent.agent import agent

    transcript = payload.get("transcript")
    confidence = float(payload.get("confidence", 1.0))
    session_id = payload.get("session_id")

    if not session_id:
        # create session and return session_id with first reply
        session_id = create_session(language="te")

    if not transcript:
        raise HTTPException(status_code=400, detail="Missing transcript")

    result = agent.process_input(session_id=session_id, transcript=transcript, confidence=confidence, language="te")

    # Synthesize reply if exists
    tts_file = None
    if result.get("reply"):
        tts_file = TMP_DIR / f"reply_{session_id}.mp3"
        text_to_speech(result["reply"], str(tts_file), lang="te")

    response = {"session_id": session_id, "status": result.get("status"), "reply": result.get("reply")}
    if tts_file:
        response["audio"] = str(tts_file)
    if result.get("eligible") is not None:
        response["eligible"] = result.get("eligible")
    if result.get("application_id"):
        response["application_id"] = result.get("application_id")

    return response


@app.get("/schemes")
def list_schemes():
    """Return the available schemes (id, name, category, short description)."""
    schemes = []
    for s in DOCUMENTS.values():
        schemes.append({
            "id": s.get("id"),
            "name": s.get("name"),
            "category": s.get("category"),
            "description": s.get("description"),
        })
    return {"schemes": schemes}


@app.get("/schemes/{scheme_id}")
def get_scheme(scheme_id: str):
    doc = get_scheme_by_id(scheme_id)
    if not doc:
        raise HTTPException(status_code=404, detail="scheme not found")
    return doc


@app.get("/ui/schemes")
def schemes_ui():
    html_file = WEB_DIR / "schemes.html"
    if not html_file.exists():
        raise HTTPException(status_code=404, detail="UI not found")
    return HTMLResponse(html_file.read_text(), status_code=200)


@app.post("/speak")
async def speak(payload: dict):
    text = payload.get("text")
    lang = payload.get("lang", "te")
    if not text:
        raise HTTPException(status_code=400, detail="Missing text")
    out = TMP_DIR / "speak.mp3"
    text_to_speech(text, str(out), lang=lang)
    return {"audio": str(out)}


@app.get("/health")
def health():
    return {"status": "ok"}
