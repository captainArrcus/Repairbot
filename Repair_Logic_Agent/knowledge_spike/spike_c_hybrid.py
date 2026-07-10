"""Spike C — Hybrid (Structured lookup + LLM fallback).

Fast path: exact error-code match -> return structured result, no LLM.
Slow path: no/low-confidence match -> LLM reasons over ONLY the top-5
candidates from Spike A (narrowed context), not the full wiki.

This tests whether pre-filtering the context improves LLM accuracy vs Spike B,
and how often we can skip the LLM entirely.
"""
import argparse
from dataclasses import dataclass, field
from pathlib import Path

from corpus_loader import (
    AlarmEntry, FaultPattern, Corpus,
    load_full_corpus, alarm_to_text, fault_pattern_to_text,
)
import spike_a_structured as spike_a
import spike_b_llm_wiki as spike_b


@dataclass
class SpikeResult:
    diagnosis: str
    labels: list[str]
    confidence: float
    source: str
    suggested_questions: list[str] = field(default_factory=list)


# Confidence at/above which we trust the structured lookup and skip the LLM.
FAST_PATH_THRESHOLD = 1.0

# Per-query path tally; the eval harness reads and resets this.
PATH_STATS = {"fast": 0, "llm": 0}


def pop_path_stats() -> dict:
    stats = dict(PATH_STATS)
    PATH_STATS["fast"] = 0
    PATH_STATS["llm"] = 0
    return stats


def _narrowed_context(candidates: list) -> str:
    """Build a small Markdown context from the top-k Spike A candidates only."""
    lines = ["# Candidate faults (pre-filtered)\n"]
    for src in candidates:
        if isinstance(src, AlarmEntry):
            lines.append(f"- {alarm_to_text(src)}")
        else:
            lines.append(f"- {fault_pattern_to_text(src)}")
    return "\n".join(lines)


def query(
    symptom_text: str,
    error_code: str | None = None,
    controller: str | None = None,
    top_k: int = 3,
    corpus: Corpus | None = None,
    corpus_dir: str | None = None,
) -> list[SpikeResult]:
    if corpus is None:
        corpus = load_full_corpus(corpus_dir)

    # --- Step 1: exact error-code lookup (fast path) ---
    code = error_code or spike_a._extract_error_code(symptom_text)
    if code:
        exact = spike_a._exact_code_match(code, corpus)
        if exact and exact[0][1] >= FAST_PATH_THRESHOLD:
            PATH_STATS["fast"] += 1
            results = [spike_a._alarm_to_result(a, conf) for a, conf in exact[:top_k]]
            return [SpikeResult(**vars(r)) for r in results]

    # --- Step 2: no confident match -> narrow, then let the LLM reason ---
    PATH_STATS["llm"] += 1
    full_query = symptom_text
    if error_code:
        full_query = f"Error code: {error_code}. {full_query}"
    if controller:
        full_query = f"Controller: {controller}. {full_query}"

    tfidf = spike_a._tfidf_search(full_query, corpus, top_k=5)
    candidates = [src for src, _ in tfidf]
    context = _narrowed_context(candidates)

    raw = spike_b._call_llm(context, full_query)
    results = [
        SpikeResult(
            diagnosis=r.get("diagnosis", ""),
            labels=r.get("labels", []),
            confidence=float(r.get("confidence", 0.0)),
            source=r.get("source", "hybrid_llm"),
            suggested_questions=r.get("suggested_questions", []),
        )
        for r in raw[:top_k]
    ]

    # Fallback: if the LLM returned nothing, degrade to Spike A's ranking so we
    # never hand back an empty result.
    if not results:
        for src, score in tfidf[:top_k]:
            if isinstance(src, AlarmEntry):
                r = spike_a._alarm_to_result(src, round(score * 0.9, 3))
            else:
                r = spike_a._fault_pattern_to_result(src, round(score * 0.7, 3))
            results.append(SpikeResult(**vars(r)))

    return results


def main():
    parser = argparse.ArgumentParser(description="Spike C: Hybrid (structured + LLM fallback)")
    parser.add_argument("--query", required=True, help="Symptom text / error description")
    parser.add_argument("--corpus", required=True, help="Path to Research_Data/ directory")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    results = query(args.query, corpus_dir=args.corpus, top_k=args.top_k)
    path = "FAST (structured, no LLM)" if PATH_STATS["fast"] else "LLM fallback"

    print(f"\n{'='*60}")
    print(f"Spike C — Hybrid")
    print(f"Query: {args.query}")
    print(f"Path used: {path}")
    print(f"{'='*60}")
    for i, r in enumerate(results, 1):
        print(f"\n  #{i}  [conf={r.confidence:.2f}]  {r.source}")
        print(f"      Diagnosis: {r.diagnosis}")
        print(f"      Labels: {r.labels}")
        if r.suggested_questions:
            print(f"      Questions: {r.suggested_questions[0]}")


if __name__ == "__main__":
    main()
