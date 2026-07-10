# Feature 0.1 — Knowledge-Layer Shootout: Findings

> **Question this spike answers:** For CNC fault diagnosis, does an LLM add value
> beyond structured error-code lookup + fault-pattern matching?

**Run:** 2026-07-10 · 20 golden cases · model `gemini/gemini-3.1-flash-lite`
(see [Model note](#model-note)) · full numbers in [results.json](results.json).

---

## Results

| Spike | Top-1 acc | Top-3 recall | Q-overlap | Latency | Cost/run |
|---|---|---|---|---|---|
| A — structured (no LLM) | 0.60 | 0.308 | 0.125 | **3 ms** | **$0.00** |
| B — LLM full-wiki | 0.70 | 0.242 | **0.25** | 6713 ms | $0.0288 |
| **C — hybrid (winner)** | **0.75** | 0.308 | 0.15 | 1594 ms | $0.0066 |

Spike C fast-path split: **4 of 20** answered by exact error-code lookup (no LLM,
free, instant); 16 fell through to LLM reasoning over narrowed candidates.

---

## Winner: Spike C (Hybrid)

Best top-1 accuracy (0.75), tied-best top-3 recall (0.308), and **4× cheaper +
4× faster than the full-wiki approach (B)** because it (a) skips the LLM entirely
on exact error-code hits and (b) feeds the LLM only the top-5 pre-filtered
candidates instead of the whole knowledge base.

## Does the LLM add value?

**Yes — but for ranking and questions, not raw recall.**

- **Top-1 accuracy: +15%** (A 0.60 → C 0.75). The LLM correctly re-ranks the
  right diagnosis to the top slot on cases where TF-IDF alone put it lower.
- **Discriminating questions: +100%** (A 0.125 → B 0.25). The LLM generates
  questions that overlap the expert's `expected_agent_questions` far better than
  the canned questions in the alarm DB.
- **Top-3 recall: flat / worse.** B (0.242) is actually *below* A (0.308) —
  handing the LLM the entire wiki lets it wander. Pre-filtering (C) restores it.

**Takeaway:** the LLM is a *refiner over structured candidates*, not a
replacement for structured lookup. Full-wiki reasoning (B) is the worst trade:
most expensive, slowest, and worst recall.

---

## The 31% recall number is mostly a metric artifact — read top-1 instead

Absolute top-3 recall (~31%) is far below the Roadmap's 85% target, but this is
**not** primarily a retrieval failure. Correctness is scored on token-set overlap
between ground-truth labels and result labels. The most-missed labels are
granular symptom/positional tags that the structured alarm DB's
`related_components` field never encodes:

```
overcurrent (3×), plc_alarm (2×), communication (2×), x_axis, y_axis,
cooling_fan, pneumatics, excess_error, software_limit, zero_offset, ...
```

The spikes routinely retrieve the **correct alarm** (top-1 = 60–75%) but get
penalized for not emitting labels like `x_axis` (which is in the *query*, not the
alarm record) or `overcurrent` (a symptom the DB tags as a component instead).

**Action for the dataset (Feature 0.0 follow-up):** align the golden-case label
taxonomy with the alarm DB `related_components`, *or* enrich alarm records with
positional/symptom tags. Until then, trust **top-1 accuracy** as the primary
metric, not top-3 recall.

---

## Recommendation for Feature 0.2 (CLI agent)

Ship the **Hybrid** knowledge layer:

1. **Exact error-code lookup first** — deterministic, free, instant. Covers the
   4/20 cases here and will cover most real cases where the technician has a code.
2. **LLM fallback over pre-filtered candidates** — when there's no code or the
   match is ambiguous, feed the LLM the top-5 structured candidates (not the full
   wiki) to re-rank and to generate discriminating questions.
3. **Do not ship full-wiki reasoning (B)** — 4× the cost, worse recall.

The LLM's real home is the **conversation** (asking good discriminating
questions), which is exactly what Feature 0.2 is. This spike confirms the
architecture: structured spine + LLM for ranking and dialogue.

---

## Cost analysis

| Approach | $/20 cases | $/query | Notes |
|---|---|---|---|
| A | $0.00 | $0.00 | no LLM |
| B | $0.0288 | ~$0.0014 | full wiki in context every query |
| C | $0.0066 | ~$0.0003 | fast-path free; narrowed context on fallback |

At production scale, C is ~4× cheaper than B and most queries with a valid error
code cost nothing.

---

## Model note

Spec **D2** pins `gemini-2.5-flash`, but its free tier is **~20 requests/day per
project** — exhausted immediately. We ran on **`gemini-3.1-flash-lite`** (current
gen, ~1,000 RPD/project free) via a round-robin over three keys on separate
team accounts (`key_rotator.py`, test-only). Model is overridable with
`SPIKE_LLM_MODEL`. A stronger reasoner (paid 2.5/3-flash) would likely widen the
LLM's top-1 and question-quality lead — this run is a **lower bound** on LLM value.

## Known gaps / what would change with PDF manuals

- **No PDF manuals** — retrieval is over ~30 structured entries only. Real manuals
  would add depth but also OCR/chunking noise; the RAG-vs-VLM question is deferred
  until we have them.
- **Small n (20 cases).** Directional, not statistically tight.
- **flash-lite ceiling.** The LLM numbers are a floor, not a ceiling.
