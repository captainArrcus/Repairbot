# Feature 0.1 — Knowledge-Layer Shootout: Requirements

> **One sentence:** Evaluate which knowledge retrieval approach best matches CNC fault symptoms to the correct diagnosis, using the structured dataset we already have.

---

## Context

Feature 0.0 (golden dataset) was defined in the Roadmap as a prerequisite. We have a partial but usable version of it:

| Asset | Status | Location |
|---|---|---|
| Golden test cases | **4 cases** (of 20 target) | `Research_Data/07_golden_test_cases/golden_cases.yaml` |
| SINUMERIK alarm DB | **15 alarms**, richly structured | `Research_Data/01_error_code_databases/sinumerik_alarms.yaml` |
| Heidenhain error DB | **8 errors**, minimal structure | `Research_Data/01_error_code_databases/heidenhain_errors.yaml` |
| Fanuc alarm DB | **9 alarms**, minimal structure | `Research_Data/01_error_code_databases/fanuc_alarms.yaml` |
| Mechanical fault patterns | **3 component patterns** | `Research_Data/04_fault_pattern_corpus/mechanical_faults.yaml` |
| Service manual PDFs | **0 PDFs** (registry only) | `Research_Data/02_service_manuals/manual_registry.yaml` |
| StepRunner (smolagents) | Working, tested | `Repair_Logic_Agent/agents/agent_runner.py` |

> **IMPORTANT:** We have no PDF manuals. The Roadmap assumed `docs/` would contain 20 relevant PDF pages. Our real dataset is structured YAML — error codes, fault patterns, and golden cases. The spike must be designed around this reality.

---

## Scope

### In Scope

1. **Adapt the three spike approaches** to work with structured YAML data (not PDFs):
   - **Spike A — Structured Lookup + Semantic Search:** Load error code DBs + fault patterns into an in-memory index. Match queries via exact error code lookup + semantic similarity over `probable_causes`, `symptoms`, `recommended_actions` fields.
   - **Spike B — LLM-as-Reasoner (compiled context):** Compile all structured knowledge into a single Markdown "wiki" document. Feed this as context to an LLM along with the query. Let the LLM reason over it directly.
   - **Spike C — Hybrid (Structured lookup + LLM fallback):** Exact error code lookup first; if found, return structured data. If ambiguous or not found, fall back to LLM reasoning over the full corpus.

2. **Evaluation harness** that runs each spike against the golden cases and measures:
   - **Top-1 accuracy:** Does the top result match `ground_truth_diagnosis`?
   - **Top-3 recall:** Do the top-3 results contain the correct `ground_truth_labels`?
   - **Discriminating question quality:** Does the spike suggest questions that overlap with `expected_agent_questions`?

3. **Expand golden cases** from 4 to at least 10 before running the evaluation, using the existing alarm databases as source material.

4. **Results report** — a `results.json` + human-readable summary documenting which approach won and why.

### Out of Scope

| Item | Why Not Now |
|---|---|
| PDF ingestion / OCR pipeline | No PDFs exist yet. Build this when we have manuals. |
| VLM page-feed spike | Requires page images. Not applicable to structured data. |
| Vector database (FAISS, Qdrant) | Premature. In-memory search over ~30 alarm entries is instant. |
| Integration with CLI agent (Feature 0.2) | Separate feature. The winning approach becomes a tool in 0.2. |
| Production-quality code | This is a spike. Exploration code with clear interfaces. |

---

## Key Decisions

### D1: No FAISS for 30 entries

The Roadmap specifies `faiss-cpu` and `sentence-transformers`. With ~30 alarm entries and ~3 fault patterns, a vector database is engineering theater. We use:
- **Exact match** for error codes (dictionary lookup)
- **TF-IDF or simple embedding similarity** over cause/symptom text fields (scikit-learn or a small sentence-transformer model)
- If sentence-transformers proves necessary, use `all-MiniLM-L6-v2` (fast, small, multilingual-capable)

### D2: LLM calls use LiteLLM via existing API keys

The `.env` already has `GOOGLE_API_KEY` for Gemini. We use `gemini/gemini-2.5-flash` via LiteLLM as the primary model for Spike B and Spike C. This validates the LiteLLM integration path simultaneously.

### D3: Evaluation is deterministic where possible

- Spike A (structured lookup) is fully deterministic — no LLM calls.
- Spikes B and C use `temperature=0` for reproducibility.
- Golden case matching uses exact label overlap, not fuzzy matching.

### D4: The real question this spike answers

The Roadmap frames this as "RAG vs VLM vs Wiki." With our actual data, the real question is:

> **"For CNC fault diagnosis, does an LLM add value beyond structured error code lookup + fault pattern matching?"**

If Spike A (no LLM) achieves ≥85% top-3 recall on structured data, the LLM's primary value is in the *conversation* (Feature 0.2), not the *retrieval*. This is a critical architectural finding.

### D5: Golden cases must be expanded before the spike is meaningful

4 cases is too few for statistical validity. We expand to 10+ by:
- Mining the SINUMERIK alarm DB (15 entries with rich `probable_causes`)
- Creating realistic symptom descriptions that map to these alarms
- Ensuring coverage across all three controller families

---

## Dependencies

| Dependency | Status | Risk |
|---|---|---|
| Python 3.12+ | Assumed installed | Low |
| `litellm` + API key | In `requirements.txt` + `.env` | Low — keys present |
| `PyYAML` | In `requirements.txt` | None |
| `scikit-learn` (for TF-IDF) | **Not yet in requirements.txt** | Low — add it |
| `sentence-transformers` (optional) | **Not yet in requirements.txt** | Medium — large download |
| Golden cases ≥10 | **Currently 4** | Medium — must expand first |

---

## Terminology

| Term | Meaning in this feature |
|---|---|
| **Spike** | A throwaway prototype to answer a specific technical question |
| **Golden case** | A test case with known ground truth diagnosis and labels |
| **Top-k recall** | Fraction of golden cases where the correct labels appear in the top-k results |
| **Structured lookup** | Exact or near-exact match against error code databases |
| **LLM-as-reasoner** | Using an LLM to reason over provided context (not RAG — the full corpus fits in context) |

---

*Feature 0.1 · Stand: 02. Juni 2026*
