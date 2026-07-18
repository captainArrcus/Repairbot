"""Feature 2.4: STT pipeline.

Unit tests run everywhere (fake model). The WER test needs the ffmpeg binary
and downloads the tiny Whisper weights on first run (~39 MB, cached); the
sample is a committed gTTS render (no offline TTS exists — spec D5) with
seeded noise mixed in at test time.
"""

import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app import config
from app.services import agent_service
from app.tools import stt

FIXTURE = Path(__file__).parent / "fixtures" / "sample_de.mp3"
# what the fixture speaks (normalized like _normalize output)
REFERENCE = "die maschine zeigt fehlercode al 309 und die x achse rattert beim verfahren"

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg binary not installed"
)


def _normalize(text: str) -> list[str]:
    return "".join(c if c.isalnum() else " " for c in text.lower()).split()


def _wer(reference: list[str], hypothesis: list[str]) -> float:
    """Word error rate = word-level Levenshtein distance / reference length."""
    previous = list(range(len(hypothesis) + 1))
    for i, ref_word in enumerate(reference, 1):
        current = [i]
        for j, hyp_word in enumerate(hypothesis, 1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (ref_word != hyp_word),
                )
            )
        previous = current
    return previous[-1] / len(reference)


def test_wer_metric():
    assert _wer(["a", "b", "c"], ["a", "b", "c"]) == 0.0
    assert _wer(["a", "b", "c"], ["a", "x", "c"]) == pytest.approx(1 / 3)
    assert _wer(["a", "b"], []) == 1.0


class _FakeModel:
    device = SimpleNamespace(type="cpu")

    def transcribe(self, audio, **kwargs):
        return {
            "text": " AL 309 an der X-Achse ",
            "language": "de",
            "segments": [
                {
                    "words": [
                        {"word": " AL", "start": 0.0, "end": 0.31, "probability": 0.9},
                        {"word": " 309", "start": 0.31, "end": 0.84, "probability": 0.7},
                    ]
                }
            ],
        }


def test_result_shape_and_confidence(monkeypatch):
    monkeypatch.setattr(stt, "_model", _FakeModel)
    result = stt._transcribe_array(np.zeros(stt.SAMPLE_RATE, dtype=np.float32))
    assert result["transcript"] == "AL 309 an der X-Achse"
    assert result["language"] == "de"
    assert result["words"][0] == {"word": "AL", "start": 0.0, "end": 0.31, "probability": 0.9}
    assert result["confidence"] == pytest.approx(0.8)


def test_non_audio_object_rejected(monkeypatch):
    monkeypatch.setattr(stt.storage, "get_object", lambda k: (b"x", "image/png"))
    with pytest.raises(ValueError, match="not audio"):
        stt.transcribe("some-key")


def test_stt_step_failure_never_raises(monkeypatch):
    # broken audio must never 500 the turn (agent_service failure path)
    def boom(media_key):
        raise RuntimeError("ffmpeg exploded")

    monkeypatch.setattr(agent_service.stt, "transcribe", boom)
    events: list = []
    tools_called: list = []
    assert agent_service._stt_step("key", events, tools_called) == ""
    assert events[-1].result_summary.startswith("transcription failed")
    assert tools_called[0]["tool"] == "stt"


@pytest.fixture
def base_model(monkeypatch):
    # tiny garbles German even on clean audio (measured, spec D6); base is the
    # smallest model that transcribes the sample usefully
    monkeypatch.setattr(config, "WHISPER_MODEL", "base")
    stt._model.cache_clear()
    yield
    stt._model.cache_clear()


@needs_ffmpeg
def test_noisy_sample_wer_measured_and_logged(base_model):
    """Roadmap acceptance: WER on sample noisy audio, measured and logged."""
    clean = stt._decode(FIXTURE.read_bytes())
    rng = np.random.default_rng(2404)
    signal_rms = float(np.sqrt(np.mean(clean**2)))
    # ~10 dB SNR — loud factory floor
    noisy = clean + rng.normal(0.0, signal_rms / np.sqrt(10), clean.shape).astype(np.float32)

    result = stt._transcribe_array(stt._reduce_noise(noisy))

    wer = _wer(_normalize(REFERENCE), _normalize(result["transcript"]))
    print(
        f"\nSTT sample (base, 10 dB SNR): WER={wer:.2f}, "
        f"confidence={result['confidence']}, transcript={result['transcript']!r}"
    )
    assert result["words"], "expected word-level timestamps"
    assert all(w["end"] >= w["start"] >= 0 for w in result["words"])
    assert 0 < result["confidence"] <= 1
    assert wer <= 0.5  # ceiling so a silent STT regression fails; large-v3 does better
