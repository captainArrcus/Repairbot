"""Spike B — LLM-as-Reasoner (Wiki Compile).

Compiles the full knowledge corpus into a Markdown document, then uses
an LLM to reason over it for each query.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from dotenv import load_dotenv
import litellm

from corpus_loader import (
    Corpus, load_full_corpus, alarm_to_text, fault_pattern_to_text,
)
import key_rotator

# Load API keys from .env
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass
class SpikeResult:
    diagnosis: str
    labels: list[str]
    confidence: float
    source: str
    suggested_questions: list[str] = field(default_factory=list)


WIKI_PATH = Path(__file__).resolve().parent / "compiled_wiki.md"
WIKI_HASH_PATH = Path(__file__).resolve().parent / ".wiki_hash"

# Spec D2 pins gemini-2.5-flash, but its free tier is only 20 requests/day/project.
# Override via env (e.g. gemini/gemini-2.0-flash, ~200/day) to run the eval on the
# free tier without exhausting quota. Production keeps the spec default.
LLM_MODEL = os.getenv("SPIKE_LLM_MODEL", "gemini/gemini-2.5-flash")

# Running LLM cost tally. The eval harness pops this between spikes to attribute
# cost per approach (Spike C reuses _call_llm below, so its cost lands here too).
_cost_accumulator = {"usd": 0.0}


def pop_cost() -> float:
    """Return accumulated LLM cost (USD) since last pop, then reset to 0."""
    c = _cost_accumulator["usd"]
    _cost_accumulator["usd"] = 0.0
    return c


# Client-side throttle so bursts stay under the model's requests-per-minute
# quota (Gemini free tier ~10 RPM -> ~6s spacing). Rotating over N keys lets us
# fire N times as fast, so divide the global interval by the key count.
# ponytail: min-interval gate, swap for a token-bucket only if we parallelize.
_MIN_INTERVAL_S = float(os.getenv("LLM_MIN_INTERVAL_S", "6")) / max(1, key_rotator.key_count())
_last_call = {"t": 0.0}


def _throttle():
    elapsed = time.time() - _last_call["t"]
    if elapsed < _MIN_INTERVAL_S:
        time.sleep(_MIN_INTERVAL_S - elapsed)
    _last_call["t"] = time.time()

SYSTEM_PROMPT = """You are a CNC machine diagnostic expert. You have access to a knowledge base of error codes, alarm descriptions, and fault patterns for SINUMERIK, Heidenhain, and Fanuc controllers.

Given a technician's symptom description, you must:
1. Identify the most likely diagnosis (root cause)
2. Provide relevant labels (component keywords)
3. Rate your confidence (0.0-1.0) — be honest, not inflated
4. Suggest 1-3 discriminating questions to narrow down the diagnosis

IMPORTANT: Reason ONLY from the provided knowledge base below. Do not use pre-training knowledge about CNC machines.

Respond with a JSON array of up to 3 results, each with this exact schema:
```json
[
  {
    "diagnosis": "short root cause description",
    "labels": ["component1", "component2"],
    "confidence": 0.85,
    "source": "which alarm or pattern this comes from",
    "suggested_questions": ["question 1", "question 2"]
  }
]
```

Respond ONLY with the JSON array, no other text."""


def _corpus_hash(corpus: Corpus) -> str:
    """Hash corpus content to detect changes."""
    content = ""
    for a in corpus.alarms:
        content += alarm_to_text(a)
    for fp in corpus.fault_patterns:
        content += fault_pattern_to_text(fp)
    return hashlib.md5(content.encode()).hexdigest()


def compile_wiki(corpus: Corpus) -> str:
    """Convert full corpus into a Markdown wiki document."""
    lines = ["# CNC Machine Knowledge Base\n"]

    # Group alarms by controller family
    by_family: dict[str, list] = {}
    for alarm in corpus.alarms:
        by_family.setdefault(alarm.controller_family, []).append(alarm)

    for family, alarms in sorted(by_family.items()):
        lines.append(f"\n## {family}\n")
        for alarm in alarms:
            lines.append(f"### {alarm.code} — {alarm.message_en}")
            lines.append(f"- **Category:** {alarm.category}")
            if alarm.probable_causes:
                lines.append("- **Probable causes:**")
                for cause in alarm.probable_causes:
                    lines.append(f"  - {cause}")
            if alarm.recommended_actions:
                lines.append("- **Recommended actions:**")
                for action in alarm.recommended_actions:
                    lines.append(f"  - {action}")
            if alarm.related_components:
                lines.append(f"- **Components:** {', '.join(alarm.related_components)}")
            if alarm.discriminating_questions:
                lines.append("- **Discriminating questions:**")
                for dq in alarm.discriminating_questions:
                    q = dq.get("question", str(dq)) if isinstance(dq, dict) else str(dq)
                    lines.append(f"  - {q}")
            lines.append("")

    # Fault patterns
    if corpus.fault_patterns:
        lines.append("\n## Mechanical Fault Patterns\n")
        for fp in corpus.fault_patterns:
            lines.append(f"### {fp.component}")
            if fp.symptoms:
                lines.append("- **Symptoms:**")
                for s in fp.symptoms:
                    lines.append(f"  - {s}")
            for rc in fp.root_causes:
                cause = rc.get("cause", "")
                lines.append(f"- **Root cause:** {cause}")
                for check in rc.get("checks", []):
                    lines.append(f"  - Check: {check}")
            lines.append("")

    return "\n".join(lines)


def _get_or_compile_wiki(corpus: Corpus) -> str:
    """Return cached wiki if corpus hasn't changed, otherwise recompile."""
    current_hash = _corpus_hash(corpus)

    if WIKI_PATH.exists() and WIKI_HASH_PATH.exists():
        cached_hash = WIKI_HASH_PATH.read_text().strip()
        if cached_hash == current_hash:
            return WIKI_PATH.read_text()

    wiki = compile_wiki(corpus)
    WIKI_PATH.write_text(wiki)
    WIKI_HASH_PATH.write_text(current_hash)
    return wiki


def _call_llm(wiki: str, symptom_text: str, max_retries: int = 3) -> list[dict]:
    """Call LLM with wiki context and symptom query. Retry with backoff."""
    user_msg = f"""## Knowledge Base

{wiki}

---

## Technician's Report

{symptom_text}

Provide your diagnosis as a JSON array."""

    for attempt in range(max_retries):
        try:
            _throttle()
            response = litellm.completion(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0,
                response_format={"type": "json_object"},
                api_key=key_rotator.next_key(),
            )
            try:
                _cost_accumulator["usd"] += litellm.completion_cost(completion_response=response)
            except Exception:
                pass  # ponytail: cost is best-effort; missing pricing shouldn't kill a run
            raw = response.choices[0].message.content.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()

            parsed = json.loads(raw)
            # Handle both direct array and wrapped object
            if isinstance(parsed, dict):
                for key in ("results", "diagnoses", "items"):
                    if key in parsed:
                        parsed = parsed[key]
                        break
                else:
                    parsed = [parsed]
            return parsed

        except Exception as e:
            if attempt < max_retries - 1:
                # Rate limits reset per-minute, so wait long enough to clear the
                # window rather than a few seconds: 15s, 30s, 45s.
                wait = 15 * (attempt + 1)
                print(f"  LLM call failed ({e}), retrying in {wait}s...", file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"  LLM call failed after {max_retries} attempts: {e}", file=sys.stderr)
                return []


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

    wiki = _get_or_compile_wiki(corpus)

    full_query = symptom_text
    if error_code:
        full_query = f"Error code: {error_code}. {full_query}"
    if controller:
        full_query = f"Controller: {controller}. {full_query}"

    raw_results = _call_llm(wiki, full_query)

    results = []
    for r in raw_results[:top_k]:
        results.append(SpikeResult(
            diagnosis=r.get("diagnosis", ""),
            labels=r.get("labels", []),
            confidence=float(r.get("confidence", 0.0)),
            source=r.get("source", "llm_wiki"),
            suggested_questions=r.get("suggested_questions", []),
        ))

    return results


def main():
    parser = argparse.ArgumentParser(description="Spike B: LLM Wiki Compile")
    parser.add_argument("--query", required=True, help="Symptom text / error description")
    parser.add_argument("--corpus", required=True, help="Path to Research_Data/ directory")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    results = query(args.query, corpus_dir=args.corpus, top_k=args.top_k)

    print(f"\n{'='*60}")
    print(f"Spike B — LLM Wiki Compile")
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
