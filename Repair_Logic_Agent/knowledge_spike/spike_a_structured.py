"""Spike A — Structured Lookup + TF-IDF Text Similarity.

No LLM calls. Pure error code matching + text similarity over the corpus.
"""
import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from corpus_loader import (
    AlarmEntry, FaultPattern, Corpus,
    load_full_corpus, alarm_to_text, fault_pattern_to_text,
)


@dataclass
class SpikeResult:
    diagnosis: str
    labels: list[str]
    confidence: float
    source: str
    suggested_questions: list[str] = field(default_factory=list)


def _extract_error_code(text: str) -> str | None:
    """Try to parse an error/alarm code from free text."""
    patterns = [
        r"(?:AL|F|SV|SP|PS|OT|OH|EX|ERROR)\s*\d+",
        r"\b\d{3,6}\b",
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return None


def _normalize_code(code: str) -> str:
    """Normalize codes for comparison: strip whitespace, uppercase."""
    return re.sub(r"\s+", " ", code.strip().upper())


def _exact_code_match(code: str, corpus: Corpus) -> list[tuple[AlarmEntry, float]]:
    """Find exact code matches in alarm database."""
    normalized = _normalize_code(code)
    matches = []
    for alarm in corpus.alarms:
        if _normalize_code(alarm.code) == normalized:
            matches.append((alarm, 1.0))
    return matches


def _tfidf_search(query: str, corpus: Corpus, top_k: int = 5) -> list[tuple[AlarmEntry | FaultPattern, float]]:
    """TF-IDF cosine similarity search over the full corpus."""
    texts = []
    sources = []

    for alarm in corpus.alarms:
        texts.append(alarm_to_text(alarm))
        sources.append(alarm)

    for fp in corpus.fault_patterns:
        texts.append(fault_pattern_to_text(fp))
        sources.append(fp)

    if not texts:
        return []

    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    tfidf_matrix = vectorizer.fit_transform(texts + [query])

    query_vec = tfidf_matrix[-1]
    corpus_matrix = tfidf_matrix[:-1]

    similarities = cosine_similarity(query_vec, corpus_matrix).flatten()
    ranked = sorted(enumerate(similarities), key=lambda x: x[1], reverse=True)

    results = []
    for idx, score in ranked[:top_k]:
        if score > 0.0:
            results.append((sources[idx], float(score)))

    return results


def _alarm_to_result(alarm: AlarmEntry, confidence: float) -> SpikeResult:
    """Convert an AlarmEntry to a SpikeResult."""
    questions = []
    for dq in alarm.discriminating_questions:
        if isinstance(dq, dict):
            questions.append(dq.get("question", str(dq)))
        else:
            questions.append(str(dq))

    # Build a diagnosis string from the alarm
    diagnosis = alarm.message_en
    if alarm.probable_causes:
        diagnosis = alarm.probable_causes[0]

    return SpikeResult(
        diagnosis=diagnosis,
        labels=list(alarm.related_components),
        confidence=confidence,
        source=f"{alarm.controller_family} {alarm.code}",
        suggested_questions=questions or alarm.recommended_actions[:2],
    )


def _fault_pattern_to_result(fp: FaultPattern, confidence: float) -> SpikeResult:
    """Convert a FaultPattern to a SpikeResult."""
    causes = [rc.get("cause", "") for rc in fp.root_causes]
    checks = []
    for rc in fp.root_causes:
        checks.extend(rc.get("checks", []))

    return SpikeResult(
        diagnosis=causes[0] if causes else fp.component,
        labels=[fp.component.lower().replace(" ", "_").replace("/", "_")],
        confidence=confidence,
        source=f"fault_pattern:{fp.component}",
        suggested_questions=checks[:3],
    )


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

    results = []

    # Step 1: Try exact code match
    code = error_code or _extract_error_code(symptom_text)
    if code:
        exact_matches = _exact_code_match(code, corpus)
        for alarm, conf in exact_matches:
            results.append(_alarm_to_result(alarm, conf))

    # Step 2: TF-IDF fallback / augmentation
    full_query = symptom_text
    if controller:
        full_query = f"{controller} {full_query}"

    tfidf_matches = _tfidf_search(full_query, corpus, top_k=top_k + 3)
    for source, score in tfidf_matches:
        # Skip if already in results from exact match
        if isinstance(source, AlarmEntry):
            if any(r.source == f"{source.controller_family} {source.code}" for r in results):
                # Boost confidence of exact match
                continue
            results.append(_alarm_to_result(source, round(score * 0.9, 3)))
        else:
            results.append(_fault_pattern_to_result(source, round(score * 0.7, 3)))

    # Sort by confidence, deduplicate, limit
    results.sort(key=lambda r: r.confidence, reverse=True)
    return results[:top_k]


def main():
    parser = argparse.ArgumentParser(description="Spike A: Structured Lookup + TF-IDF")
    parser.add_argument("--query", required=True, help="Symptom text / error description")
    parser.add_argument("--corpus", required=True, help="Path to Research_Data/ directory")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    results = query(args.query, corpus_dir=args.corpus, top_k=args.top_k)

    print(f"\n{'='*60}")
    print(f"Spike A — Structured Lookup + TF-IDF")
    print(f"Query: {args.query}")
    print(f"{'='*60}")
    for i, r in enumerate(results, 1):
        print(f"\n  #{i}  [conf={r.confidence:.2f}]  {r.source}")
        print(f"      Diagnosis: {r.diagnosis}")
        print(f"      Labels: {r.labels}")
        if r.suggested_questions:
            print(f"      Questions: {r.suggested_questions[0]}")


if __name__ == "__main__":
    main()
