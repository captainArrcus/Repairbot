# Feature 2.4 — Plan

1. `pyproject.toml`: add `openai-whisper`, `noisereduce`; `uv sync`.
   CI: ffmpeg on the apt line. `.env`: `WHISPER_MODEL=base` (no GPU).
2. `app/config.py`: `WHISPER_MODEL` (default `large-v3`), `STT_LANGUAGE`
   (default `de`)
3. `app/services/storage.py`: `head_content_type(media_key) -> str`
4. `app/tools/stt.py`
   - `transcribe(media_key) -> dict` (S3 shell + audio/* guard) over
     `_decode` (ffmpeg via whisper.load_audio) → `_reduce_noise`
     (noisereduce) → `_transcribe_array` (cached model, word timestamps,
     mean-probability confidence)
5. `app/services/agent_service.py`: `_split_media` by stored MIME;
   `_stt_step` per audio key (cap 3) BEFORE the user-turn INSERT; transcript
   joins turn text; stt events prepended to the agent event list; vision now
   gets only visual keys
6. Tests
   - `tests/stt/test_transcribe_sample.py`: WER metric sanity, result
     shape/confidence (fake model), non-audio rejection, failure path never
     raises, noisy-sample WER measured + logged (ffmpeg-gated, base model,
     committed gTTS fixture + seeded noise)
   - `tests/test_sessions.py`: audio-turn flow test (DB-gated, STT mocked) —
     routing, events, transcript persisted as user-turn content
7. Verify: `uv run pytest`, `uv run ruff check/format`, live acceptance run
   (presign PUT of the fixture mp3 → turn → SSE shows stt events, AL 309
   hypotheses, transcript in user turn) with `base`
8. FINDINGS.md; Roadmap 2.4 → DONE (background-job wording amended, D1);
   Techstack: noisereduce in the dependency list, STT row → implemented
