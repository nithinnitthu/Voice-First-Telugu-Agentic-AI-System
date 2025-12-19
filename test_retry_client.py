from clients.retry_client import RetryClient


class FakeServer:
    """Simulate /transcribe then /transcribe success on retry, and /agent call.

    Supports a 'new_file_created' flag which can be set by a fake recorder to emulate
    creating a new audio file for retry paths.
    """

    def __init__(self):
        self.calls = 0
        self.new_file_created = False

    def post_transcribe(self, path, files=None):
        self.calls += 1
        # if a new file was recorded (or files indicate a new path), return a high-confidence transcription
        if self.new_file_created or (files and files.get("path") == "new_audio.wav"):
            return {"text": "నేను ప్రభుత్వ పథకాల కోసం దరఖాస్తు చేయాలనుకుంటున్నాను", "confidence": 0.95, "low_confidence": False}

        # otherwise: simulate low-confidence on the first call, success on subsequent calls
        if self.calls == 1:
            return {"text": "గోపాల్", "confidence": 0.2, "low_confidence": True, "clarify_prompt": "క్షమించండి, మళ్ళీ చెప్పండి"}

        return {"text": "నేను ప్రభుత్వ పథకాల కోసం దరఖాస్తు చేయాలనుకుంటున్నాను", "confidence": 0.95, "low_confidence": False}

    def post_agent(self, json):
        return {"session_id": "sess-1", "status": "asked_age", "reply": "దయచేసి మీ వయస్సు చెప్పండి."}

class DummyRequests:
    def __init__(self, fake_server: FakeServer):
        self.fake = fake_server

    def post(self, url, files=None, json=None):
        class Resp:
            def __init__(self, data):
                self._data = data
                self.status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return self._data

        if url.endswith('/transcribe'):
            return Resp(self.fake.post_transcribe(None, files=files))
        if url.endswith('/agent'):
            return Resp(self.fake.post_agent(json))
        if url.endswith('/speak'):
            return Resp({"audio": "speak.mp3"})
        raise RuntimeError("Unknown endpoint")


def test_retry_client_simulated():
    fake = FakeServer()
    dummy = DummyRequests(fake)
    client = RetryClient(server_url="http://localhost:8000")
    # inject requests-like object
    client.requests = dummy  # not used by default methods; we'll monkeypatch methods

    # monkeypatch methods to use dummy
    client.transcribe_file = lambda p: dummy.post("/transcribe", files={}).json()
    client.call_agent = lambda t, c, session_id=None: dummy.post("/agent", json={}).json()

    resp = client.run_flow("dummy.mp3", auto_retry=True)
    assert resp is not None
    assert resp.get("status") == "asked_age"
    print("Simulated retry flow passed")


def test_auto_rerecord_simulated():
    fake = FakeServer()
    dummy = DummyRequests(fake)

    # record_fn simulates creating a new audio file by setting a flag on fake
    def fake_record():
        fake.new_file_created = True
        return "new_audio.wav"

    client = RetryClient(server_url="http://localhost:8000", auto_record=True, record_fn=fake_record)

    # monkeypatch transcribe to send the 'path' so FakeServer can detect it's the new file
    def transcribe_with_path(p):
        return dummy.post("/transcribe", files={"path": p}).json()

    client.transcribe_file = transcribe_with_path
    client.call_agent = lambda t, c, session_id=None: dummy.post("/agent", json={}).json()

    resp = client.run_flow("orig.mp3", auto_retry=False)
    assert resp is not None
    assert resp.get("status") == "asked_age"
    # ensure the fake recorded file was used
    assert fake.new_file_created is True
    print("Auto re-record simulated flow passed")
