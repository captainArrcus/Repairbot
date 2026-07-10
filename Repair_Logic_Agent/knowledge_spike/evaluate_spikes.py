"""Evaluation harness — the knowledge-layer shootout.

Runs Spike A / B / C against the golden cases and reports Top-1 accuracy,
Top-3 label recall, discriminating-question overlap, latency, and LLM cost.

Matching note: golden diagnoses/labels are snake_case tokens (e.g.
`ball_screw_bearing_worn`) while spikes emit free-text diagnoses and component
labels. Exact string equality is meaningless here, so correctness is scored on
TOKEN-SET overlap between a ground-truth label and any result label (subset or
equality after splitting on `_`). See FINDINGS.md for the rationale.
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus_loader import load_full_corpus, load_golden_cases
import spike_a_structured as spike_a
import spike_b_llm_wiki as spike_b
import spike_c_hybrid as spike_c

SPIKES = {
    "spike_a_structured": spike_a,
    "spike_b_llm_wiki": spike_b,
    "spike_c_hybrid": spike_c,
}

_STOP = {"the", "and", "you", "are", "does", "this", "that", "with", "when",
         "what", "is", "it", "a", "of", "to", "on", "in", "or", "do", "can",
         "at", "all", "any", "for", "your"}


def _tok(label: str) -> set[str]:
    """Split a label/diagnosis into normalized word tokens."""
    return {t for t in label.lower().replace("/", "_").replace(" ", "_").split("_") if t}


def _label_hit(gt_label: str, result_labels: list[str]) -> bool:
    """A ground-truth label is 'hit' if its token set has a subset/superset
    relation with any result label's token set (e.g. gt `ball_screw` matches
    result `ball_screw_bearing`), but not merely a shared generic token."""
    gt = _tok(gt_label)
    if not gt:
        return False
    for rl in result_labels:
        r = _tok(rl)
        if gt <= r or r <= gt:
            return True
    return False


def _top1_correct(result, case) -> bool:
    """Top result is correct if it hits at least one ground-truth label, or its
    diagnosis tokens overlap the ground-truth diagnosis tokens."""
    if not result:
        return False
    top = result[0]
    if any(_label_hit(gt, top.labels) for gt in case.ground_truth_labels):
        return True
    gt_diag = _tok(case.ground_truth_diagnosis)
    return len(gt_diag & _tok(top.diagnosis)) >= 2


def _top3_recall(result, case) -> float:
    """Fraction of ground-truth labels found across the top-3 result labels."""
    gt = case.ground_truth_labels
    if not gt:
        return 0.0
    all_labels = [l for r in result[:3] for l in r.labels]
    hits = sum(1 for g in gt if _label_hit(g, all_labels))
    return hits / len(gt)


def _question_covered(expected: str, suggested: list[str]) -> bool:
    """Expected question is covered if some suggested question shares >=2
    content words (len>=4, non-stopword) with it."""
    exp = {w for w in _tok(expected) if len(w) >= 4 and w not in _STOP}
    if not exp:
        return False
    for s in suggested:
        sug = {w for w in _tok(s) if len(w) >= 4 and w not in _STOP}
        if len(exp & sug) >= 2:
            return True
    return False


def _question_overlap(result, case) -> float:
    exp = case.expected_agent_questions
    if not exp:
        return 0.0
    suggested = [q for r in result[:3] for q in r.suggested_questions]
    covered = sum(1 for e in exp if _question_covered(e, suggested))
    return covered / len(exp)


def evaluate_spike(name, mod, cases, corpus) -> dict:
    top1, top3, qov, latencies = [], [], [], []
    for case in cases:
        t0 = time.perf_counter()
        try:
            result = mod.query(
                case.symptom_text,
                error_code=case.error_code,
                controller=case.controller,
                top_k=3,
                corpus=corpus,
            )
        except Exception as e:
            print(f"  [{name}] case {case.id} errored: {e}", file=sys.stderr)
            result = []
        latencies.append((time.perf_counter() - t0) * 1000)
        top1.append(1.0 if _top1_correct(result, case) else 0.0)
        top3.append(_top3_recall(result, case))
        qov.append(_question_overlap(result, case))

    n = len(cases)
    stats = {
        "top1_accuracy": round(sum(top1) / n, 3),
        "top3_recall": round(sum(top3) / n, 3),
        "question_overlap": round(sum(qov) / n, 3),
        "avg_latency_ms": round(sum(latencies) / n, 1),
        "total_llm_cost_usd": round(spike_b.pop_cost(), 6),
    }
    if name == "spike_c_hybrid":
        stats["path_split"] = spike_c.pop_path_stats()
    return stats


def main():
    parser = argparse.ArgumentParser(description="Knowledge-layer shootout")
    parser.add_argument("--cases", required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    cases = load_golden_cases(args.cases)
    corpus = load_full_corpus(args.corpus)
    spike_b.pop_cost()  # zero the tally before we start

    results = {}
    for name, mod in SPIKES.items():
        print(f"Running {name} over {len(cases)} cases...", file=sys.stderr)
        results[name] = evaluate_spike(name, mod, cases, corpus)

    # Winner: best top-1 accuracy (the trustworthy signal on this label set),
    # tie-broken by top-3 recall.
    winner = max(results, key=lambda k: (results[k]["top1_accuracy"], results[k]["top3_recall"]))
    a = results["spike_a_structured"]
    w = results[winner]
    top1_gain = round(w["top1_accuracy"] - a["top1_accuracy"], 3)
    recall_gain = round(w["top3_recall"] - a["top3_recall"], 3)
    recommendation = (
        f"{winner} wins: top-1 {w['top1_accuracy']:.0%}, top-3 {w['top3_recall']:.0%}, "
        f"${w['total_llm_cost_usd']:.4f}/run. "
        f"LLM value-add over pure structured lookup: top-1 {top1_gain:+.0%}, "
        f"top-3 recall {recall_gain:+.0%}. "
        + ("The LLM improves the top result but not top-3 recall — best used to "
           "re-rank/refine structured candidates, not replace them."
           if top1_gain > 0.05 and recall_gain <= 0.05 else
           "The LLM adds little; structured lookup carries the retrieval."
           if top1_gain <= 0.05 else
           "The LLM materially improves retrieval — invest in the LLM path.")
    )

    output = {
        "run_date": datetime.now().isoformat(timespec="seconds"),
        "num_cases": len(cases),
        "spikes": results,
        "winner": winner,
        "recommendation": recommendation,
    }
    Path(args.output).write_text(json.dumps(output, indent=2))

    # Human-readable summary
    print(f"\n{'='*72}")
    print(f"KNOWLEDGE-LAYER SHOOTOUT — {len(cases)} golden cases")
    print(f"{'='*72}")
    hdr = f"{'spike':<22}{'top1':>8}{'top3':>8}{'q-ovlp':>9}{'lat(ms)':>10}{'cost$':>10}"
    print(hdr)
    print("-" * len(hdr))
    for name, s in results.items():
        mark = " *" if name == winner else ""
        print(f"{name:<22}{s['top1_accuracy']:>8.2f}{s['top3_recall']:>8.2f}"
              f"{s['question_overlap']:>9.2f}{s['avg_latency_ms']:>10.1f}"
              f"{s['total_llm_cost_usd']:>10.4f}{mark}")
    if "path_split" in results["spike_c_hybrid"]:
        ps = results["spike_c_hybrid"]["path_split"]
        print(f"\nSpike C path split: {ps['fast']} fast (no LLM) / {ps['llm']} LLM fallback")
    print(f"\nWinner: {winner}")
    print(f"Recommendation: {recommendation}")
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
