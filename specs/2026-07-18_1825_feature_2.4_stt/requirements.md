# Feature 2.4 — STT (Whisper) + audio preprocessing: Requirements

> **One sentence:** `app/tools/stt.py` turns an uploaded voice note
> (media_key) into a German transcript with word timestamps and confidence —
> noise-reduced, locally transcribed via Whisper — and the turn handler routes
> audio media to it so the transcript becomes user-turn text and drives the
> same diagnosis paths as typed text.

---

## Context

The Roadmap pipeline: fetch audio from S3 → noise reduction → Whisper
(large-v3) → transcript with word timestamps and confidence. The upload path
already exists (Feature 1.2 presigns `audio/*`); the 2.3 FINDINGS left the
explicit pointer: "Route by content type in the turn handler when audio
lands." Transcripts feed the exact same code-extraction fast path and
full-text slow path as typed text (2.2/2.3) — STT is an input adapter, not a
new reasoning path.

## Scope (from Roadmap Feature 2.4)

1. `app/tools/stt.py` — `def transcribe(media_key: str) -> dict`
2. `app/services/storage.py` — gains `head_content_type` (media routing)
3. `app/services/agent_service.py` — audio keys → STT before the user turn is
   persisted; `stt` tool_call/tool_result events; transcript = user-turn text
4. `tests/stt/test_transcribe_sample.py` (+ audio flow test in
   `tests/test_sessions.py`); CI installs ffmpeg

Out of scope: streaming/live STT, speaker separation, language auto-detect
beyond Whisper's own (Phase 1 is German — Techstack), hermes registration of
the tool (2.5).

## Decisions

### D1: Whisper runs in-process and synchronously — no background job

The Roadmap parenthetical says "STT runs via background job", but the entire
turn pipeline is synchronous-inline by design since 1.3 (events persisted
before streaming; vision runs inline too, 2.3). A job queue would be new
infra for one tool. A voice note is seconds long; `base` on CPU transcribes
it in single-digit seconds — same ballpark as the vision LLM fallback. Runs
inside `handle_turn` like every other tool; 2.5 (which owns the agent-side
restructuring anyway) revisits if real latency data demands it. Roadmap text
updated accordingly.

### D2: Model size is config (`WHISPER_MODEL`), default large-v3, dev = base

Techstack/Roadmap mandate large-v3 — that stays the default. The dev box has
no GPU; large-v3 on CPU is unusable (minutes per clip), so `.env` sets
`base`, and tests pin `base` too (`tiny` garbles German even on clean audio —
measured, see FINDINGS). The model is lazily loaded once per
process (`lru_cache`); whisper/torch imports are function-local — importing
torch costs seconds and only audio turns pay.

### D3: Noise reduction = noisereduce (spectral gating), always on

Roadmap offers "noisereduce or RNNoise wrapper". noisereduce is a plain-PyPI
dep operating directly on the numpy array Whisper wants; RNNoise needs a
native wrapper. Techstack names spectral subtraction/noise gating — that is
literally what noisereduce does. Applied unconditionally at **softened
strength (`prop_decrease=0.75`)**: full-strength gating measurably destroys
Whisper's input (it is noise-robust by training — see FINDINGS), 0.75 is
neutral on white noise and keeps headroom for real non-stationary factory
hum. The strength constant is the calibration knob for field recordings.

### D4: Decoding = ffmpeg via `whisper.load_audio` — one decoder for every container

The phone will send whatever the browser records (webm/opus, m4a, mp3).
ffmpeg (system binary, like tesseract in 2.3) decodes all of them to the
16 kHz mono float32 array Whisper expects — no python audio-format deps.
Tests skip without the binary; CI installs it (one word on the existing apt
line; GitHub runners ship it anyway).

### D5: Sample audio = committed gTTS render + noise mixed at test time

No recorded audio exists anywhere in the repo, and the box has no offline
TTS (no espeak-ng) — audio cannot be synthesized offline the way 2.3
rendered panels. One-time gTTS render (German diagnostic sentence naming
AL 309) is committed as `tests/stt/fixtures/sample_de.mp3` (55 KB — small
enough to live in git; the binary-free rule from 2.3 D8 bends rather than
having no acceptance sample at all). Deterministic seeded gaussian noise at
~10 dB SNR is mixed at test time, so the WER test controls its own noise
level and stays reproducible.

### D6: WER measured and logged in-test, generous ceiling asserted

Roadmap acceptance is "WER measured and logged" — no threshold given. The
test computes word-level Levenshtein WER (≈15 lines, stdlib — jiwer would be
a dependency for one function), prints it, and asserts a generous ceiling
(≤ 0.5 with `base`) so a silent STT regression still fails CI. The measured
value (0.38 at 10 dB SNR) is recorded in FINDINGS.

### D7: Transcript becomes user-turn text — transcription happens BEFORE the
user turn is persisted

Roadmap acceptance: "transcripts appear as user-turn text when user uploads
audio." So `_process_turn` splits media by stored MIME (`head_content_type`
— trustworthy, the presign signs it), transcribes audio keys (cap 3, like
vision), and joins transcripts onto the turn text before the INSERT. The
Data Bridge then contains the transcript as user content with the audio key
in `media_refs`; export needs no change. STT `tool_call`/`tool_result`
events (raw result incl. words + confidence) stream at the head of the agent
turn. Failures (broken recording, ffmpeg, S3) become a failure-summary
tool_result — never a 500 (2.3 pattern). Idempotent retries return the
stored turn before any transcription runs.

### D8: Return shape

```python
{
  "transcript": str,            # stripped full text
  "language": str,              # whisper-reported (forced "de" — STT_LANGUAGE)
  "words": [{"word", "start", "end", "probability"}, ...],
  "confidence": float,          # mean word probability, 0.0 if no words
}
```

`transcribe(media_key)` raises `ValueError` for non-audio content types.
Internals split as decode → denoise → transcribe functions so tests inject
noisy arrays without S3/ffmpeg mocking.

---

## Acceptance (Roadmap)

- WER on sample noisy audio measured and logged by
  `tests/stt/test_transcribe_sample.py`.
- Audio turn → agent streams `stt` tool_call/tool_result; transcript is
  persisted as the user turn's content; a voice note naming a seeded code
  yields the same hypotheses as typing it.

---

*Feature 2.4 · Stand: 18. Juli 2026*
