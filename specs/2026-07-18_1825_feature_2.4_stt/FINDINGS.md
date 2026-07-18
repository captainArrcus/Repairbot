# Feature 2.4 — STT (Whisper) + audio preprocessing: Findings / Acceptance

**Status: COMPLETE (dev-verified, 2026-07-18). `app/tools/stt.py` transcribes
uploaded voice notes (ffmpeg decode → softened noisereduce → local Whisper,
German, word timestamps + confidence); the turn handler routes media by
stored MIME and persists the transcript as user-turn text.**

## Acceptance evidence

| Check | Result |
|---|---|
| `uv run pytest -q` | **45 passed** (39 existing + 5 new in tests/stt/ + 1 audio flow test) |
| `uv run ruff check` + `format --check` (CI scope) | clean |
| WER on sample noisy audio (Roadmap: measured and logged) | **0.38** at 10 dB SNR, `base` model, confidence 0.69 (committed gTTS sample + seeded gaussian noise, spec D5/D6) |
| Live flow (presign PUT of voice note `audio/mpeg` → audio-only turn) | thinking → `stt` tool_call/result (confidence 0.808, transcript `"Die Maschine zeigt Fehler-Code AL309 und die X-Axe ratert beim Verfahren."`) → `error_code_lookup` exact match AL 309 → 4 cause hypotheses → tactile question → done |
| Transcript = user-turn text (Roadmap acceptance) | `diagnostic_turns.content` of the user turn contains the transcript verbatim; audio key in `media_refs` |
| Media routing | audio → `stt`, images still → `vision_analysis` (2.3 flow test unchanged); unreadable keys fall to the visual failure path |

## Findings

- **Full-strength noise reduction destroys Whisper's input.** Measured on the
  seeded-noise sample: noisereduce at default `prop_decrease=1.0` turns a
  decent transcription into garbage (hallucinated Chinese tokens) on both
  `tiny` and `base` — Whisper is noise-robust by training and wants the noise
  left in rather than gating artifacts. `prop_decrease=0.75` is neutral on
  white noise; kept because real factory hum is non-stationary, where
  spectral gating actually earns its keep. `_NOISE_REDUCTION_STRENGTH` is the
  calibration knob — re-tune against field recordings when they exist.
- **`tiny` is too weak for German** — garbles even the clean sample
  ("Fehlerkot all 399"). `base` is the smallest useful model (clean sample →
  "Fehler-Code AL309", exactly what `extract_codes` needs); the WER test pins
  `base` (~139 MB download, cached).
- **The transcript walks the existing paths untouched**: "AL309" from speech
  normalizes to AL 309 via the 2.2 lookup exactly like typed or OCR'd input.
  STT is an input adapter — zero new reasoning code.
- **No recorded audio exists in the repo** (mirror of 2.3's photo situation).
  The sample is a one-time gTTS render committed as a 55 KB mp3 (no offline
  TTS on the box; a binary fixture beats no acceptance sample). Real
  field-audio WER is a runbook item once the 1.4 field test records voice.

## Notes for later features

- **2.5 (hermes):** register `transcribe(media_key)` as the `stt` hermes
  tool; revisit inline-vs-background there (spec D1) — the synchronous turn
  is the stub's shape, not the tool's.
- **Language:** forced German (`STT_LANGUAGE=de`). Techstack's "agent
  auto-detects user language" is a 2.5-agent concern; the knob already
  exists.
- **Runbooks:** field recordings from the 1.4 field test → re-run
  `tests/stt/` WER measurement and re-tune `_NOISE_REDUCTION_STRENGTH`;
  large-v3 stays the prod default (needs GPU — CPU dev boxes set
  `WHISPER_MODEL=base` in `.env`).

## Deviations from Roadmap (ratified in requirements.md)

- **No background job** — STT runs inline in the synchronous turn pipeline
  like every other tool (D1); 2.5's agent restructuring owns the revisit.
- **Noise reduction softened to 0.75** — the Roadmap's noise-reduction step
  at full strength measurably *hurts* Whisper (D3, finding above).
- **Model size is config** — large-v3 (Roadmap/Techstack) is the default;
  the no-GPU dev box runs `base`, tests run `base` (D2/D6).

---

*Feature 2.4 · Stand: 18. Juli 2026*
