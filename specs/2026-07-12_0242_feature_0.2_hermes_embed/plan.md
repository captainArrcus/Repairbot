# Feature 0.2 — hermes embed spike: Plan

> **Goal:** Embed `run_agent.AIAgent` behind `HermesAgentService`, run a real diagnostic
> conversation from a CLI, and produce a GO/NO-GO on hermes with evidence for the four
> spike questions.

---

## Task Group 1: Pinned install

1.1. Create dedicated venv `.venv-hermes` (Python 3.13; hermes requires `>=3.11,<3.14`).

1.2. Install:
```bash
uv venv --python 3.13 .venv-hermes
VIRTUAL_ENV=$PWD/.venv-hermes uv pip install \
  "hermes-agent @ git+https://github.com/NousResearch/hermes-agent@4281151ae859241351ba14d8c7682dc67ff4c126" \
  scikit-learn
```
(`scikit-learn` is for the TF-IDF narrowing in the knowledge tool; everything else the
tool needs — pyyaml, python-dotenv — is already in hermes' pins.)

1.3. Record install friction (dependency weight, conflicts) — it is evidence for the bet.

**Output:** importable `run_agent.AIAgent` at the pinned commit.

---

## Task Group 2: Knowledge tool adapter

2.1. In `hermes_service.py`, wrap `knowledge_spike/spike_a_structured.py` (via `sys.path`)
as `knowledge_retrieval(query: str) -> str` (JSON):
- extract/lookup exact error code → full alarm records, `path: "exact"`
- else → top-5 TF-IDF candidates flattened to text, `path: "narrowed_candidates"`

2.2. Corpus (`Research_Data/`) loaded once, lazily, at first tool call.

**Output:** one pure-Python tool, no LLM inside, no new retrieval code.

---

## Task Group 3: `HermesAgentService` (the embed)

3.1. Set `HERMES_HOME` (tenant-scoped dir) **before** importing hermes modules.

3.2. Register the tool: `tools.registry.registry.register(name="knowledge_retrieval",
toolset="repair_knowledge", schema=..., handler=...)` +
`toolsets.create_custom_toolset("repair_knowledge", ...)`.

3.3. Construct `AIAgent` with: `base_url`/`api_key`/`model` from env,
`enabled_toolsets=["repair_knowledge"]`, `save_trajectories=True`, `quiet_mode=True`,
`ephemeral_system_prompt=DIAGNOSTIC_PROTOCOL`, tool/stream callbacks wired to the event mapper.

3.4. Event mapper: line-buffered NDJSON parser over stream deltas → validated `StepEvent`s;
tool callbacks → `tool_call`/`tool_result`; invalid lines → sanitized `thinking`.

3.5. Allowlist assertion at `start_session`: resolved tool defs must contain
`knowledge_retrieval` and none of terminal/browser/code-exec/delegate; log the full list.

3.6. `handle_user_turn` drives `agent.run_conversation(...)`, carries conversation history
across turns, returns the ordered `list[StepEvent]`.

**Output:** `Repair_Logic_Agent/agents/hermes_service.py`.

---

## Task Group 4: CLI

4.1. `run_cli.py` — REPL: `technician>` input → events stream to stdout as
`[event_type] {json}` lines; every event also appended to
`agents/logs/session_<id>.jsonl` (the "typed step JSON per step" acceptance).

**Output:** `Repair_Logic_Agent/agents/run_cli.py`.

---

## Task Group 5: Spike checks (the four questions)

`spike_checks.py`, one check per question, evidence written to `spike_results.json`:

| # | Check | Pass criterion |
|---|---|---|
| Q1 | Scripted 2-turn AL 309 session | ≥1 `hypothesis` + ≥1 `question` typed event in turn 1; `tool_call`/`tool_result` present; `diagnosis` by turn 2 |
| Q2 | Synthetic skill in `HERMES_HOME/skills/` + memory manager | skill text reaches the built system prompt; memory manager initializes with ≥1 provider in library mode |
| Q3 | Two subprocesses, distinct `HERMES_HOME`, tenant markers A/B | marker A appears nowhere under home B and vice versa |
| Q4 | `save_trajectories=True` | `trajectory_samples.jsonl` exists, parses, contains the session incl. tool call |

**Output:** `spike_results.json` + captured transcripts.

---

## Task Group 6: FINDINGS + GO/NO-GO

6.1. `FINDINGS.md` in this spec folder: the four answers with evidence, what hermes injects
beyond our allowlist, install friction, and the GO/NO-GO decision (+ escape-hatch trigger
review per Techstack).

6.2. Copy `spike_results.json` into the spec folder for the record.

---

## File Map

```
Repair_Logic_Agent/agents/
├── hermes_service.py        # Task Groups 2+3
├── run_cli.py               # Task Group 4
├── spike_checks.py          # Task Group 5
├── requirements_agents.txt  # Task Group 1 (pinned install line)
└── logs/                    # generated — typed step JSON per session
specs/2026-07-12_0242_feature_0.2_hermes_embed/
├── requirements.md
├── plan.md
├── FINDINGS.md              # Task Group 6
└── spike_results.json       # Task Group 6
```

## Estimated Effort

| Task Group | Effort |
|---|---|
| 1. Pinned install | 0.5h |
| 2. Knowledge tool | 1h |
| 3. Service embed | 4h |
| 4. CLI | 1h |
| 5. Spike checks | 3h |
| 6. FINDINGS | 1h |
| **Total** | **~10.5h** (Roadmap estimate: 32h) |

---

*Feature 0.2 · Stand: 12. Juli 2026*
