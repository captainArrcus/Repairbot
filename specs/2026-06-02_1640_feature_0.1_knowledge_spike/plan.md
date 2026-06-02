# Feature 0.1 — Knowledge-Layer Shootout: Plan

> **Goal:** Determine which knowledge retrieval approach gives the best diagnostic accuracy on our CNC fault dataset, producing a clear winner (or hybrid recommendation) for Feature 0.2.

---

## Task Group 1: Expand the Golden Dataset (prerequisite)

**Why first:** 4 golden cases are too few. We need ≥10 for the evaluation to be meaningful.

1.1. **Review existing alarm databases** for cases with rich `probable_causes` and `discriminating_questions` fields. Priority: SINUMERIK (most detailed), then synthesize from Heidenhain and Fanuc.

1.2. **Write 6+ additional golden cases** in the same YAML schema as `golden_cases.yaml`:
   - At least 2 more SINUMERIK cases (cover spindle, tool changer, encoder faults)
   - At least 2 more Heidenhain cases
   - At least 1 more Fanuc case
   - At least 1 "ambiguous" case (symptom matches multiple alarms) — this tests discrimination ability

1.3. **Add `expected_top3_labels` field** to each golden case — the set of labels that any correct top-3 result must contain.

1.4. **Validate expanded dataset** — write a small `validate_golden.py` script that checks YAML schema consistency.

**Output:** `Research_Data/07_golden_test_cases/golden_cases.yaml` with ≥10 cases, all validated.

---

## Task Group 2: Build the Knowledge Corpus Loader

**Why:** All three spikes need to consume the same data. Build a shared loader once.

2.1. **Create `knowledge_spike/corpus_loader.py`** with functions:
   ```python
   def load_alarm_db(yaml_path: str) -> list[AlarmEntry]
   def load_fault_patterns(yaml_path: str) -> list[FaultPattern]
   def load_golden_cases(yaml_path: str) -> list[GoldenCase]
   def load_full_corpus(data_dir: str) -> Corpus
   ```
   Use simple dataclasses (not Pydantic — this is a spike).

2.2. **Create unified text representation** for each alarm/fault entry — a function that flattens structured fields into a searchable text string:
   ```python
   def alarm_to_text(alarm: AlarmEntry) -> str
   # Returns: "SINUMERIK_840D_sl | AL 309 | Axis: Following error too large | Causes: Ball screw bearing worn, Coupling loose... | Actions: Check axial play..."
   ```

2.3. **Add `requirements_spike.txt`** with spike-specific dependencies (kept separate from `Repair_Logic_Agent/requirements.txt`):
   ```
   scikit-learn>=1.5
   litellm>=1.77
   PyYAML>=6.0
   python-dotenv>=1.1
   ```

**Output:** Working `corpus_loader.py` that all spikes import.

---

## Task Group 3: Spike A — Structured Lookup + Text Similarity

**What this tests:** "Can we match symptoms to diagnoses without any LLM?"

3.1. **Create `knowledge_spike/spike_a_structured.py`:**
   - **Error code exact match:** Parse error code from query string (regex), look up in alarm DB dict.
   - **Text similarity fallback:** If no exact code match (or to rank multiple results), compute TF-IDF cosine similarity between query text and all `alarm_to_text()` representations.
   - Return top-k results as `list[SpikeResult]` with `diagnosis`, `labels`, `confidence`, `source`.

3.2. **Interface contract** (all spikes implement this):
   ```python
   @dataclass
   class SpikeResult:
       diagnosis: str
       labels: list[str]
       confidence: float
       source: str  # which alarm/pattern produced this
       suggested_questions: list[str]

   def query(symptom_text: str, error_code: str | None, controller: str | None, top_k: int = 3) -> list[SpikeResult]
   ```

3.3. **Test manually** with golden case sin_001 ("AL 309, rattling X-axis") — should return ball_screw_bearing as top result.

**Output:** Working `spike_a_structured.py`.

---

## Task Group 4: Spike B — LLM-as-Reasoner (Wiki Compile)

**What this tests:** "If we give an LLM our entire knowledge base as context, can it reason to the correct diagnosis?"

4.1. **Create `knowledge_spike/spike_b_llm_wiki.py`:**
   - **compile_wiki():** Convert all alarm DBs + fault patterns into a single Markdown document (the "wiki"). This is a one-time operation, output saved to `knowledge_spike/compiled_wiki.md`.
   - **query():** Send the wiki + query to `gemini/gemini-2.5-flash` via LiteLLM. System prompt instructs the model to return structured JSON with diagnosis, labels, confidence, and discriminating questions.

4.2. **Prompt design:** The system prompt must instruct the LLM to:
   - Return exactly the `SpikeResult` schema as JSON
   - Reason over the provided wiki, not its pre-training knowledge
   - Suggest 1–3 discriminating questions
   - Rate its confidence (0.0–1.0) honestly

4.3. **Cache compiled wiki** — don't regenerate on every query. Only regenerate when corpus data changes.

4.4. **Handle rate limits and failures gracefully** — retry with exponential backoff, fail after 3 attempts.

**Output:** Working `spike_b_llm_wiki.py` + `compiled_wiki.md`.

---

## Task Group 5: Spike C — Hybrid (Structured + LLM Fallback)

**What this tests:** "Does combining exact lookup with LLM reasoning beat either alone?"

5.1. **Create `knowledge_spike/spike_c_hybrid.py`:**
   - **Step 1:** Run Spike A's error code exact match.
   - **Step 2:** If exact match found with high confidence, return it directly (no LLM call — saves tokens and latency).
   - **Step 3:** If no match or low confidence, call LLM with the narrowed context (only related alarms, not the full wiki) to reason and refine.

5.2. **Key design point:** The LLM prompt in Spike C is *narrower* than Spike B — it only sees the top-5 candidates from Spike A, not the full corpus. This tests whether pre-filtering improves LLM accuracy.

5.3. **Track metrics:** Log whether each query used the fast path (no LLM) or the LLM fallback, and the latency/cost of each.

**Output:** Working `spike_c_hybrid.py`.

---

## Task Group 6: Evaluation Harness

**What this produces:** The shootout results.

6.1. **Create `knowledge_spike/evaluate_spikes.py`:**
   - Loads golden cases
   - Runs each spike's `query()` function against each case
   - Computes metrics per spike:
     - **Top-1 accuracy:** `result[0].diagnosis == case.ground_truth_diagnosis`
     - **Top-3 label recall:** `len(set(result_labels) & set(case.ground_truth_labels)) / len(case.ground_truth_labels)`
     - **Question overlap:** How many of `case.expected_agent_questions` are semantically covered by `result.suggested_questions` (simple substring match is sufficient for a spike)
   - Computes aggregate metrics (mean across all cases)

6.2. **Output `knowledge_spike/results.json`:**
   ```json
   {
     "run_date": "2026-06-02T16:40:00",
     "num_cases": 10,
     "spikes": {
       "spike_a_structured": {
         "top1_accuracy": 0.80,
         "top3_recall": 0.90,
         "question_overlap": 0.60,
         "avg_latency_ms": 5,
         "total_llm_cost_usd": 0.0
       },
       "spike_b_llm_wiki": { ... },
       "spike_c_hybrid": { ... }
     },
     "winner": "spike_c_hybrid",
     "recommendation": "..."
   }
   ```

6.3. **CLI interface:**
   ```bash
   python knowledge_spike/evaluate_spikes.py \
     --cases Research_Data/07_golden_test_cases/golden_cases.yaml \
     --corpus Research_Data/ \
     --output knowledge_spike/results.json
   ```

6.4. **Print human-readable summary table** to stdout after writing JSON.

**Output:** Working `evaluate_spikes.py`, `results.json`.

---

## Task Group 7: Document Findings

7.1. **Write `knowledge_spike/FINDINGS.md`:**
   - Which spike won and by how much
   - What the results mean for the architecture (does the LLM add value beyond structured lookup?)
   - Recommended approach for Feature 0.2 (CLI agent)
   - Known gaps (what would change if we had PDF manuals?)
   - Cost analysis (LLM token usage per approach)

7.2. **Update this spec folder** with final results: copy `results.json` and `FINDINGS.md` into this spec folder for the historical record.

**Output:** Decision documented, ready for Feature 0.2.

---

## File Map

All spike files go in `Repair_Logic_Agent/knowledge_spike/`:

```
Repair_Logic_Agent/knowledge_spike/
├── requirements_spike.txt        # Task Group 2
├── corpus_loader.py              # Task Group 2
├── spike_a_structured.py         # Task Group 3
├── spike_b_llm_wiki.py           # Task Group 4
├── compiled_wiki.md              # Task Group 4 (generated)
├── spike_c_hybrid.py             # Task Group 5
├── evaluate_spikes.py            # Task Group 6
├── results.json                  # Task Group 6 (generated)
├── FINDINGS.md                   # Task Group 7
└── validate_golden.py            # Task Group 1
```

Golden cases remain in `Research_Data/07_golden_test_cases/golden_cases.yaml` (expanded in place).

---

## Estimated Effort

| Task Group | Effort | Notes |
|---|---|---|
| 1. Expand golden dataset | 2h | Writing realistic cases from existing alarm DBs |
| 2. Corpus loader | 1h | Simple dataclasses + YAML parsing |
| 3. Spike A (structured) | 2h | Regex + TF-IDF, no external dependencies beyond scikit-learn |
| 4. Spike B (LLM wiki) | 3h | Prompt engineering + LiteLLM integration |
| 5. Spike C (hybrid) | 2h | Combines A + LLM call |
| 6. Evaluation harness | 2h | Metrics computation + JSON/CLI output |
| 7. Document findings | 1h | Write-up of results |
| **Total** | **~13h** | Roadmap estimated 40h — scope reduction due to no PDFs |

---

*Feature 0.1 · Stand: 02. Juni 2026*
