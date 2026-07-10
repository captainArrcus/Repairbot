"""Shared corpus loader for all knowledge spikes.

Loads alarm databases, fault patterns, and golden cases from Research_Data/
into simple dataclasses that all three spikes consume.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


# --- Dataclasses ---

@dataclass
class AlarmEntry:
    code: str
    controller_family: str
    category: str
    message_en: str
    probable_causes: list[str]
    recommended_actions: list[str]
    related_components: list[str]
    manual_reference: str = ""
    discriminating_questions: list[dict] = field(default_factory=list)


@dataclass
class FaultPattern:
    component: str
    symptoms: list[str]
    root_causes: list[dict]


@dataclass
class GoldenCase:
    id: str
    controller: str
    error_code: str
    symptom_text: str
    ground_truth_diagnosis: str
    ground_truth_labels: list[str]
    expected_agent_questions: list[str]
    machine_type: str = ""


@dataclass
class Corpus:
    alarms: list[AlarmEntry]
    fault_patterns: list[FaultPattern]


# --- Loaders ---

def load_alarm_db(yaml_path: str) -> list[AlarmEntry]:
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    family = data.get("controller_family", "UNKNOWN")
    raw_key = "alarms" if "alarms" in data else "errors"
    entries = []

    for raw in data.get(raw_key, []):
        code = raw.get("code", "")
        # Skip range-style entries like "EX 1000-1999"
        if "-" in code and any(c.isdigit() for c in code.split("-")[-1]):
            if len(code.split("-")[-1].strip()) > 2:
                continue

        entries.append(AlarmEntry(
            code=code,
            controller_family=family,
            category=raw.get("category", ""),
            message_en=raw.get("message_en", ""),
            probable_causes=raw.get("probable_causes", []),
            recommended_actions=raw.get("recommended_actions", []),
            related_components=raw.get("related_components", []),
            manual_reference=raw.get("manual_reference", ""),
            discriminating_questions=raw.get("discriminating_questions", []),
        ))

    return entries


def load_fault_patterns(yaml_path: str) -> list[FaultPattern]:
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    return [
        FaultPattern(
            component=fp["component"],
            symptoms=fp.get("symptoms", []),
            root_causes=fp.get("root_causes", []),
        )
        for fp in data.get("fault_patterns", [])
    ]


def load_golden_cases(yaml_path: str) -> list[GoldenCase]:
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    return [
        GoldenCase(
            id=c["id"],
            controller=c["controller"],
            error_code=c.get("error_code", ""),
            symptom_text=c["symptom_text"],
            ground_truth_diagnosis=c["ground_truth_diagnosis"],
            ground_truth_labels=c["ground_truth_labels"],
            expected_agent_questions=c.get("expected_agent_questions", []),
            machine_type=c.get("machine_type", ""),
        )
        for c in data.get("cases", [])
    ]


def load_full_corpus(data_dir: str) -> Corpus:
    """Load all alarm DBs and fault patterns from a Research_Data/ directory."""
    data_dir = Path(data_dir)
    alarms = []
    fault_patterns = []

    # Load all alarm databases
    error_db_dir = data_dir / "01_error_code_databases"
    if error_db_dir.exists():
        for yaml_file in sorted(error_db_dir.glob("*.yaml")):
            alarms.extend(load_alarm_db(str(yaml_file)))

    # Load fault patterns
    fault_dir = data_dir / "04_fault_pattern_corpus"
    if fault_dir.exists():
        for yaml_file in sorted(fault_dir.glob("*.yaml")):
            fault_patterns.extend(load_fault_patterns(str(yaml_file)))

    return Corpus(alarms=alarms, fault_patterns=fault_patterns)


# --- Text representation ---

def alarm_to_text(alarm: AlarmEntry) -> str:
    """Flatten an alarm entry into a single searchable text string."""
    parts = [
        alarm.controller_family,
        alarm.code,
        alarm.message_en,
    ]
    if alarm.probable_causes:
        parts.append("Causes: " + ", ".join(alarm.probable_causes))
    if alarm.recommended_actions:
        parts.append("Actions: " + ", ".join(alarm.recommended_actions))
    if alarm.related_components:
        parts.append("Components: " + ", ".join(alarm.related_components))
    return " | ".join(parts)


def fault_pattern_to_text(fp: FaultPattern) -> str:
    """Flatten a fault pattern into a searchable text string."""
    parts = [fp.component]
    if fp.symptoms:
        parts.append("Symptoms: " + ", ".join(fp.symptoms))
    for rc in fp.root_causes:
        cause = rc.get("cause", "")
        checks = ", ".join(rc.get("checks", []))
        parts.append(f"Cause: {cause} — Checks: {checks}")
    return " | ".join(parts)
