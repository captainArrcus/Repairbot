"""Feature 2.4 — STT tool.

Roadmap pipeline: fetch audio from S3 → decode via ffmpeg (whisper.load_audio,
16 kHz mono) → noise reduction (noisereduce spectral gating — factory floors
are loud) → local Whisper transcription to German → transcript with word
timestamps and confidence.

Model size comes from WHISPER_MODEL (Techstack: large-v3 in production; CPU
dev boxes run base, tests run tiny). heavy imports (whisper pulls torch) are
lazy — only audio turns pay for them.
"""

import tempfile
from functools import lru_cache
from statistics import fmean

from app import config
from app.services import storage

SAMPLE_RATE = 16_000  # whisper.load_audio resamples to this


def transcribe(media_key: str) -> dict:
    """Fetch + transcribe an uploaded voice note. Raises ValueError for
    non-audio objects (stored MIME is trustworthy — presign signs it, 1.2)."""
    data, content_type = storage.get_object(media_key)
    if not content_type.startswith("audio/"):
        raise ValueError(f"{media_key} is not audio ({content_type or 'unknown type'})")
    return _transcribe_array(_reduce_noise(_decode(data)))


def _decode(data: bytes):
    """Any container ffmpeg understands → 16 kHz mono float32 numpy array."""
    import whisper

    # whisper.load_audio shells out to ffmpeg, which wants a path
    with tempfile.NamedTemporaryFile(suffix=".audio") as f:
        f.write(data)
        f.flush()
        return whisper.load_audio(f.name)


# ponytail: measured on the seeded-noise sample — full-strength gating (1.0)
# destroys Whisper's input (it is noise-robust by training), 0.75 is neutral on
# white noise and keeps headroom for real non-stationary factory hum. Tune
# against field recordings when they exist (spec D3).
_NOISE_REDUCTION_STRENGTH = 0.75


def _reduce_noise(audio):
    import noisereduce

    return noisereduce.reduce_noise(
        y=audio, sr=SAMPLE_RATE, prop_decrease=_NOISE_REDUCTION_STRENGTH
    )


@lru_cache(maxsize=1)
def _model():
    import whisper

    return whisper.load_model(config.WHISPER_MODEL)


def _transcribe_array(audio) -> dict:
    model = _model()
    result = model.transcribe(
        audio,
        language=config.STT_LANGUAGE,
        word_timestamps=True,
        fp16=model.device.type == "cuda",
    )
    words = [
        {
            "word": w["word"].strip(),
            "start": round(w["start"], 2),
            "end": round(w["end"], 2),
            "probability": round(w["probability"], 3),
        }
        for segment in result["segments"]
        for w in segment["words"]
    ]
    return {
        "transcript": result["text"].strip(),
        "language": result["language"],
        "words": words,
        "confidence": round(fmean(w["probability"] for w in words), 3) if words else 0.0,
    }
