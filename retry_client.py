#!/usr/bin/env python3
"""Client that automatically retries on ASR low confidence by following the agent's clarify prompt.
Designed to be simple and dependency-light for demos and tests.
"""
import requests
import time
from typing import Optional


class RetryClient:
    def __init__(self, server_url: str = "http://localhost:8000", max_retries: int = 3, auto_record: bool = False, record_fn=None):
        """record_fn: optional callable used to record audio during auto re-record. It should
        accept no args and return a file path to the new recording. If not provided and auto_record
        is True, a default recorder will be used (lazy imports and tempfile).
        """
        self.server = server_url.rstrip("/")
        self.max_retries = max_retries
        self.auto_record = auto_record
        # record_fn is injectable for tests; default will lazily import src.audio.record_audio.record
        self.record_fn = record_fn

    def transcribe_file(self, path: str):
        url = f"{self.server}/transcribe"
        with open(path, "rb") as f:
            files = {"file": (path, f, "audio/mp3")}
            r = requests.post(url, files=files)
        r.raise_for_status()
        return r.json()

    def call_agent(self, transcript: str, confidence: float, session_id: Optional[str] = None):
        url = f"{self.server}/agent"
        payload = {"transcript": transcript, "confidence": confidence}
        if session_id:
            payload["session_id"] = session_id
        r = requests.post(url, json=payload)
        r.raise_for_status()
        return r.json()

    def speak(self, text: str, lang: str = "te"):
        url = f"{self.server}/speak"
        r = requests.post(url, json={"text": text, "lang": lang})
        r.raise_for_status()
        return r.json()

    def run_flow(self, audio_path: str, auto_retry: bool = False):
        """Run the transcribe -> agent flow with retry on low-confidence.

        If `auto_retry` is True the client will automatically retry without prompting the user.
        """
        attempts = 0
        last_transcript = ""
        last_conf = 0.0
        session_id = None

        while attempts < self.max_retries:
            attempts += 1
            print(f"Attempt {attempts}: sending audio to /transcribe -> {audio_path}")
            resp = self.transcribe_file(audio_path)
            print("Transcribe response:", resp)
            last_transcript = resp.get("text", "")
            last_conf = float(resp.get("confidence", 0.0))

            if resp.get("low_confidence"):
                prompt = resp.get("clarify_prompt") or "I couldn't understand, please repeat."
                print("Low confidence detected. Clarify prompt (Telugu):", prompt)
                # auto_retry True will re-try immediately; otherwise interactive prompt
                if self.auto_record:
                    # perform a re-record using the injected record function or the default recorder
                    print("Auto-record is enabled: recording new audio...")
                    if self.record_fn is None:
                        # lazy import default recorder
                        try:
                            from src.audio.record_audio import record as default_record
                        except Exception:
                            # fallback: not available in this environment
                            print("Default recorder unavailable; aborting auto-record")
                            return None

                        import tempfile
                        new_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name

                        # record short 3s clip for demo
                        try:
                            default_record(duration=3.0, filename=new_file)
                        except Exception as e:
                            print("Recording failed:", e)
                            return None
                        audio_path = new_file
                    else:
                        # record_fn should return a path
                        audio_path = self.record_fn()

                    print("Re-recorded audio ->", audio_path)
                    # continue to retry with new audio_path (loop continues)
                    continue
                if auto_retry:
                    print("auto_retry=True -> retrying automatically")
                    time.sleep(0.2)
                    continue
                else:
                    ans = input("Press Enter to retry with the same file, or type 'r' to record new audio (not implemented): ")
                    if ans.strip().lower() == "r":
                        print("Recording not implemented in this CLI demo; please re-run with a new file.")
                        return None
                    else:
                        continue
            else:
                # call agent
                print("Confidence sufficient, calling /agent with transcript.")
                agent_resp = self.call_agent(last_transcript, last_conf, session_id=session_id)
                print("Agent response:", agent_resp)
                session_id = agent_resp.get("session_id", session_id)
                # Optionally fetch TTS audio
                if agent_resp.get("audio"):
                    print("Agent returned audio at:", agent_resp.get("audio"))
                return agent_resp

        print("Max retries reached; aborting.")
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Retry client for voice agent demo")
    parser.add_argument("audio", help="Path to audio file (mp3/wav)")
    parser.add_argument("--server", default="http://localhost:8000")
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()

    client = RetryClient(server_url=args.server, max_retries=args.retries)
    client.run_flow(args.audio)
