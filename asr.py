"""ASR wrapper (Whisper) with confidence scoring and cloud fallback placeholder.

Functions return a dictionary: {"text": str, "confidence": float, "raw": dict}.
Confidence is a heuristic derived from Whisper segment `avg_logprob` values and ranges between 0.0 and 1.0.
"""
from typing import Optional, Dict, Any


def _compute_confidence(result: Dict[str, Any]) -> float:
    """Compute a heuristic confidence score from Whisper's result.

    Whisper's `segments` often include `avg_logprob` (negative values). We compute the mean
    avg_logprob and map it roughly into [0, 1] as `confidence = clamp(1.0 + mean_logprob, 0.0, 1.0)`.

    This is a simple heuristic for demo/flow control (e.g., clarification prompts). Replace with
    better calibration for production.
    """
    segments = result.get("segments", []) if isinstance(result, dict) else []
    if not segments:
        return 0.0
    vals = [s.get("avg_logprob") for s in segments if s.get("avg_logprob") is not None]
    if not vals:
        return 0.0
    mean = sum(vals) / len(vals)
    conf = 1.0 + mean
    conf = max(0.0, min(1.0, conf))
    return conf


def transcribe_file(path: str, model_name: str = "small", language: Optional[str] = "te", use_cloud: bool = False) -> Dict[str, Any]:
    """Transcribe audio file at `path` and return dict with text, confidence and raw Whisper output.

    If `use_cloud` is True, this calls a placeholder cloud provider function (not implemented).
    """
    if use_cloud:
        return cloud_transcribe(path, language=language)

    try:
        import whisper
    except Exception as e:
        raise RuntimeError("Whisper is not installed. Install with `pip install openai-whisper`.") from e

    model = whisper.load_model(model_name)
    kwargs = {}
    if language:
        kwargs["language"] = language
        kwargs["task"] = "transcribe"

    result = model.transcribe(path, **kwargs)
    text = result.get("text", "").strip()
    confidence = _compute_confidence(result)
    return {"text": text, "confidence": confidence, "raw": result}


def cloud_transcribe(path: str, language: Optional[str] = "te") -> Dict[str, Any]:
    """Placeholder for cloud ASR provider. Implement provider-specific SDK calls here.
    For now this raises NotImplementedError so callers can detect and switch providers.
    """
    raise NotImplementedError("Cloud ASR provider not implemented. Use local Whisper or implement provider integration.")
