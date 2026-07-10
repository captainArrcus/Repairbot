"""Validate golden test cases YAML schema consistency."""
import argparse
import sys
import yaml


REQUIRED_FIELDS = {
    "id", "controller", "error_code", "symptom_text",
    "ground_truth_diagnosis", "ground_truth_labels", "expected_agent_questions",
}

CONTROLLER_FAMILIES = {"SINUMERIK", "Heidenhain", "Fanuc"}


def validate(cases_path: str) -> list[str]:
    with open(cases_path) as f:
        data = yaml.safe_load(f)

    cases = data.get("cases", [])
    errors = []

    if len(cases) < 10:
        errors.append(f"Only {len(cases)} cases — need at least 10.")

    ids_seen = set()
    families_seen = set()

    for i, case in enumerate(cases):
        prefix = f"Case #{i} (id={case.get('id', '???')})"

        missing = REQUIRED_FIELDS - set(case.keys())
        if missing:
            errors.append(f"{prefix}: missing fields {missing}")

        cid = case.get("id")
        if cid in ids_seen:
            errors.append(f"{prefix}: duplicate id '{cid}'")
        ids_seen.add(cid)

        controller = case.get("controller", "")
        for family in CONTROLLER_FAMILIES:
            if family.lower() in controller.lower():
                families_seen.add(family)

        labels = case.get("ground_truth_labels", [])
        if not isinstance(labels, list) or len(labels) == 0:
            errors.append(f"{prefix}: ground_truth_labels must be a non-empty list")

        questions = case.get("expected_agent_questions", [])
        if not isinstance(questions, list) or len(questions) == 0:
            errors.append(f"{prefix}: expected_agent_questions must be a non-empty list")

    missing_families = CONTROLLER_FAMILIES - families_seen
    if missing_families:
        errors.append(f"Missing controller families: {missing_families}")

    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate golden cases YAML")
    parser.add_argument("--cases", required=True, help="Path to golden_cases.yaml")
    args = parser.parse_args()

    errors = validate(args.cases)
    if errors:
        print("VALIDATION FAILED:")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)

    with open(args.cases) as f:
        count = len(yaml.safe_load(f).get("cases", []))
    print(f"✓ All {count} golden cases valid. All controller families represented.")


if __name__ == "__main__":
    main()
