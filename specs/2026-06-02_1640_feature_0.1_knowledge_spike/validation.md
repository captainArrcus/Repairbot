# Feature 0.1 — Knowledge-Layer Shootout: Validation

> **When is this feature done?** When we have a documented, data-backed recommendation for which knowledge retrieval approach to use in the CLI diagnostic agent (Feature 0.2).

---

## Acceptance Criteria

### AC1: Golden Dataset — Expanded and Validated

- [ ] `golden_cases.yaml` contains **≥10 cases**
- [ ] All three controller families are represented (SINUMERIK ≥4, Heidenhain ≥3, Fanuc ≥2)
- [ ] At least 1 "ambiguous" case (symptom plausibly matches multiple diagnoses)
- [ ] `validate_golden.py` passes with zero errors:
  ```bash
  python knowledge_spike/validate_golden.py --cases Research_Data/07_golden_test_cases/golden_cases.yaml
  ```
- [ ] Each case has: `id`, `controller`, `error_code`, `symptom_text`, `ground_truth_diagnosis`, `ground_truth_labels`, `expected_agent_questions`

### AC2: All Three Spikes Execute Successfully

- [ ] Spike A runs without errors:
  ```bash
  python knowledge_spike/spike_a_structured.py --query "AL 309 rattling X axis" --corpus Research_Data/
  ```
  Returns ≥1 result with `ball_screw` or `bearing` in labels.

- [ ] Spike B runs without errors:
  ```bash
  python knowledge_spike/spike_b_llm_wiki.py --query "AL 309 rattling X axis" --corpus Research_Data/
  ```
  Returns structured JSON result.

- [ ] Spike C runs without errors:
  ```bash
  python knowledge_spike/spike_c_hybrid.py --query "AL 309 rattling X axis" --corpus Research_Data/
  ```
  Returns result and logs whether it used the fast path or LLM fallback.

### AC3: Evaluation Harness Produces Results

- [ ] Evaluation runs end-to-end:
  ```bash
  python knowledge_spike/evaluate_spikes.py \
    --cases Research_Data/07_golden_test_cases/golden_cases.yaml \
    --corpus Research_Data/ \
    --output knowledge_spike/results.json
  ```
- [ ] `results.json` is valid JSON and contains metrics for all three spikes
- [ ] Human-readable summary table is printed to stdout
- [ ] Metrics include: `top1_accuracy`, `top3_recall`, `question_overlap`, `avg_latency_ms`

### AC4: Quality Thresholds

These are **learning thresholds**, not pass/fail gates. The spike succeeds even if no approach hits these numbers — the finding itself is valuable.

| Metric | Target | Significance |
|---|---|---|
| Top-3 recall (best spike) | ≥ 85% | Roadmap target. If met, approach is viable for production. |
| Top-1 accuracy (best spike) | ≥ 60% | Indicates the approach can be primary, not just fallback. |
| Spike A top-3 recall | Measured | If ≥85% without LLM, this is a critical architectural insight. |
| Spike B vs Spike A delta | Measured | Quantifies LLM value-add for retrieval. |
| Spike C vs Spike B delta | Measured | Quantifies whether pre-filtering helps LLM accuracy. |

### AC5: Decision Documented

- [ ] `FINDINGS.md` exists and contains:
  - Winner recommendation (or hybrid recommendation)
  - Data-backed justification with actual numbers from `results.json`
  - Implications for Feature 0.2 architecture
  - Known limitations and what would change with PDF manuals
  - Cost comparison (LLM tokens/USD per approach)
- [ ] `results.json` and `FINDINGS.md` are copied to this spec folder

---

## Test Commands (Copy-Paste Ready)

### 1. Validate golden cases
```bash
cd /home/arrcus/Schreibtisch/Projekte/repair_bot
python Repair_Logic_Agent/knowledge_spike/validate_golden.py \
  --cases Research_Data/07_golden_test_cases/golden_cases.yaml
```

### 2. Run individual spikes (smoke test)
```bash
cd /home/arrcus/Schreibtisch/Projekte/repair_bot/Repair_Logic_Agent

# Spike A — no LLM, should be instant
python knowledge_spike/spike_a_structured.py \
  --query "AL 309 rattling X axis" \
  --corpus ../Research_Data/

# Spike B — requires GOOGLE_API_KEY
python knowledge_spike/spike_b_llm_wiki.py \
  --query "AL 309 rattling X axis" \
  --corpus ../Research_Data/

# Spike C — hybrid
python knowledge_spike/spike_c_hybrid.py \
  --query "AL 309 rattling X axis" \
  --corpus ../Research_Data/
```

### 3. Run full evaluation
```bash
cd /home/arrcus/Schreibtisch/Projekte/repair_bot/Repair_Logic_Agent
python knowledge_spike/evaluate_spikes.py \
  --cases ../Research_Data/07_golden_test_cases/golden_cases.yaml \
  --corpus ../Research_Data/ \
  --output knowledge_spike/results.json
```

### 4. Verify outputs exist
```bash
ls -la Repair_Logic_Agent/knowledge_spike/results.json
ls -la Repair_Logic_Agent/knowledge_spike/FINDINGS.md
ls -la Repair_Logic_Agent/knowledge_spike/compiled_wiki.md
cat Repair_Logic_Agent/knowledge_spike/results.json | python -m json.tool
```

---

## Merge Criteria

This feature can be merged (committed to main) when:

1. **All AC1–AC5 are checked off** above
2. **No hardcoded paths** — all file paths are relative or configurable via CLI args
3. **API keys are loaded from `.env`** — no keys in source code
4. **Each spike can run independently** — `spike_a_structured.py` doesn't import from `spike_b_llm_wiki.py`
5. **The recommendation in FINDINGS.md has been reviewed** by the team and informs the Feature 0.2 design

---

## What "Failure" Looks Like (and Why It's Still Valuable)

| Scenario | What it means | Next step |
|---|---|---|
| No spike reaches 85% top-3 recall | Our structured data is too sparse for reliable retrieval | Prioritize PDF manual acquisition; redesign around Hybrid approach (Roadmap's fallback) |
| Spike A ≥ 85%, Spikes B/C don't improve | LLM doesn't add value for *retrieval* | LLM is for *conversation* only (Feature 0.2); knowledge layer is pure structured lookup |
| Spike B >> Spike A | LLM reasoning over context significantly improves accuracy | Invest in the wiki-compile approach; expand corpus compilation pipeline |
| Spike C == Spike B | Pre-filtering doesn't help | Use simpler approach (B or A) in production |
| Golden cases are too easy (all spikes get 100%) | Cases don't test discrimination | Add harder cases: ambiguous symptoms, cross-controller confusion, missing error codes |

---

*Feature 0.1 · Stand: 02. Juni 2026*
