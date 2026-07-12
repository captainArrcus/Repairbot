# Feature 0.2 — hermes embed spike: Findings

> **Question this spike answers:** Can we embed `run_agent.AIAgent` (hermes-agent) as a
> library behind our own `AgentService` and get the diagnostic loop, the learning loop,
> tenant isolation, and trajectory export — without fighting the framework?

**Run:** 2026-07-12 · pinned commit `4281151ae859241351ba14d8c7682dc67ff4c126` ·
model `gemini-3.1-flash-lite` via Google's OpenAI-compatible endpoint ·
evidence in [spike_results.json](spike_results.json), CLI transcript in
[cli_acceptance_transcript.txt](cli_acceptance_transcript.txt).

---

## Verdict: **GO** — all four spike questions pass

| # | Question | Answer | Evidence |
|---|---|---|---|
| Q1 | Streaming → typed SSE events? | **YES** | Turn 1 streams `tool_call → tool_result → thinking → 3× hypothesis → question → done`; turn 2 `thinking → 3× hypothesis (updated confidences, 2 eliminated) → diagnosis → guidance → done`. Both turns in 4.0 s total. |
| Q2 | Skills/memory in pure library mode? | **YES** (config caveats below) | Pre-seeded skill appears in the built system-prompt skills index; file-based `MemoryStore` active; `memory` + 3 skill tools exposed. No CLI/gateway involved anywhere. |
| Q3 | Per-`HERMES_HOME` isolation? | **YES** | Two *parallel* subprocess sessions, tenant markers A/B. Full-tree scan: marker A appears in zero files under home B and vice versa; each home persisted its own marker. |
| Q4 | Trajectory export? | **YES** | `trajectory_samples.jsonl` (ShareGPT format) written automatically with `save_trajectories=True`; 2 entries incl. the `knowledge_retrieval` tool call — directly consumable by hermes' datagen/`trajectory_compressor` tooling (Feature 2.7). |

The Techstack escape-hatch trigger ("monkey-patching hermes internals, fighting single-user
assumptions, learning loop needs the gateway") was **not** hit. Zero hermes code modified;
everything is constructor arguments, one registry call, and one config file.

---

## Acceptance transcript (Roadmap example, verbatim run)

`python run_cli.py` → input `"Controller: SINUMERIK 840D, AL 309. Rattling when jogging X."`
The agent called `knowledge_retrieval` (exact fast-path hit), streamed 3 ranked hypotheses,
then asked — as the Roadmap example predicted — for a tactile axial-play check in mm.
Second turn ("0.5mm Spiel") eliminated h2/h3, diagnosed worn ball-screw thrust bearings at
0.95 confidence, and issued `safety_level: "high"` guidance. Every step logged as typed JSON
(`agents/logs/session_*.jsonl`).

---

## What we had to learn (the integration cost, honestly)

1. **Tool registration wants the *bare* function schema.** `tools.registry.register(schema=...)`
   wraps it in the OpenAI envelope itself; passing the pre-wrapped form produces an HTTP 400
   (`Unknown name "type" at 'tools[0].function'`). One-line fix.
2. **The learning loop is delivered *through hermes' own tools*.** The skills index is only
   injected into the system prompt when `skills_list`/`skill_view`/`skill_manage` are among
   the agent's valid tools, and memory needs the `memory` tool. A literal 4-domain-tool
   allowlist silently starves the learning loop — the very reason we chose hermes.
   **Techstack amendment (ratified 2026-07-12):** allowlist = our domain tools **+ hermes learning tools**
   (`skills_list`, `skill_view`, `skill_manage`, `memory`). All file-based, tenant-scoped, no
   code execution. Verified exposure in this spike is exactly:
   `['knowledge_retrieval', 'memory', 'skill_manage', 'skill_view', 'skills_list']` —
   no terminal, no browser, no code-exec, no delegation (asserted at every `start_session`).
3. **Memory is config-gated per tenant home.** `agent_init` reads `memory.memory_enabled`
   (default **false**) from `HERMES_HOME/config.yaml`. `hermes_service` writes a minimal
   config into each fresh tenant home.
4. **Skills are index-only in the prompt** — name + description; bodies load on demand via
   `skill_view`. Correct design (token-cheap), just don't test for the body in the prompt.
5. **Trajectories append to the process CWD**, not `HERMES_HOME`. Feature 2.7's collector
   must run the agent with a tenant-scoped working directory (the spike does).
6. **`ephemeral_system_prompt` is appended** to hermes' built prompt (identity + skills +
   memory scaffolding stay intact) — the right injection point for our diagnostic protocol.
7. **Observed egress beyond the LLM endpoint:** hermes fetched model metadata
   (`models_dev_cache.json`) on first boot. Harmless, but the Feature 2.5 egress-proxy
   allowlist must either permit models.dev or pre-seed the cache. Also auto-created:
   `SOUL.md` (identity bootstrap) — tenant-scoped, harmless.
8. **Install weight:** hermes exact-pins a heavy tree (openai 2.24, numpy 2.4, faster-whisper,
   python-telegram-bot, google-api-client, …). Dedicated venv (`.venv-hermes`) required —
   documented in `agents/requirements_agents.txt`. Python `>=3.11,<3.14`.
9. **Good ops behavior observed:** on the 400 error, hermes classified it non-retryable,
   aborted cleanly, and wrote a request debug dump into the tenant's `sessions/` dir.

## Design decisions that held up

- **The agent IS the LLM half of the 0.1 hybrid.** `knowledge_retrieval` returns structured
  data only (exact alarm record, else top-5 TF-IDF candidates); the embedded agent reasons
  over it. AL 309 hit the exact fast-path — zero retrieval LLM cost.
- **Event mapping:** typed events are parsed post-turn from the returned message history
  (deterministic ordering of `tool_call`/`tool_result`/NDJSON protocol lines). Live callbacks
  (`tool_start/complete`, `stream_delta`) exist and fire — Feature 1.3 wires them to SSE push.
  Model discipline on the NDJSON protocol was perfect across all runs on flash-lite.
- **Model endpoint:** `AIAgent` speaks OpenAI protocol to any `base_url` — confirmed against
  Google's endpoint. Production LiteLLM proxy = env-var swap (`REPAIR_LLM_BASE_URL`);
  Claude fallback via `AIAgent(fallback_model=...)` is available but unexercised (no key).

## Open items → later features

| Item | Where it lands |
|---|---|
| Live SSE push from stream callbacks (incl. Last-Event-ID replay) | Feature 1.3 |
| Pydantic validation of events (spike validates required fields, dataclass-based) | Feature 1.3 |
| Media turns (`media_paths` raises NotImplementedError today) | Features 2.3/2.4 |
| Egress isolation container + models.dev allowlist decision | Feature 2.5 |
| Trajectory upload to S3 + skill curation queue (`skill_manage` creates skills autonomously — curation gate needed before fleet sharing) | Feature 2.7 |
| Multi-session concurrency inside ONE process (spike isolates per process; per-process-per-tenant is also the deployment model) | Feature 2.5 |

---

*Feature 0.2 · Stand: 12. Juli 2026 · Decision: **GO** — hermes-agent is the backbone.*
