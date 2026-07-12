"""Feature 0.2 — the four hermes spike questions, answered with runnable evidence.

Usage (inside .venv-hermes):
    python spike_checks.py [--output spike_results.json]

Q1 streaming structure -> typed events   Q3 per-HERMES_HOME tenant isolation
Q2 skills/memory in pure library mode    Q4 trajectory export

Internal: --worker --home DIR --marker STR runs one isolated tenant session (Q3).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

_AGENTS_DIR = Path(__file__).resolve().parent

TURN_1 = "Controller: SINUMERIK 840D, error AL 309. Rattling sound when jogging the X-axis."
TURN_2 = "I can push the table by hand, there is about 0.5 mm of axial play."

SKILL_MARKER = "SKILLMARKER-AL309-AXIALSPIEL"
SKILL_MD = f"""---
name: al309-axial-play-check
description: Werkstatt procedure to check X-axis axial play when SINUMERIK AL 309 is suspected.
version: 1.0.0
---

# AL 309 axial play check ({SKILL_MARKER})

1. Move the X-axis table to mid travel, controller in JOG mode.
2. Mount a dial gauge against the table edge.
3. Push/pull the table by hand; more than 0.05 mm of play indicates a worn
   ball screw bearing.
"""


def _fresh_home(name: str) -> Path:
    home = _AGENTS_DIR / ".hermes_home" / name
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True)
    return home


def _new_service(home: Path, api_key_env: str = "GOOGLE_API_KEY"):
    from hermes_service import HermesAgentService
    return HermesAgentService(hermes_home=str(home), api_key=os.getenv(api_key_env))


def _event_types(events) -> list[str]:
    return [e.type for e in events]


# --- Q1 + Q2 + Q4 share one real session (keeps free-tier LLM calls low) ---

def run_main_session() -> dict:
    home = _fresh_home("tenant_main")
    skill_dir = home / "skills" / "al309-axial-play-check"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(SKILL_MD)

    os.chdir(home)  # hermes appends trajectory_samples.jsonl to cwd
    svc = _new_service(home)
    svc.start_session("spike_main")

    t0 = time.time()
    ev1 = svc.handle_user_turn(TURN_1)
    ev2 = svc.handle_user_turn(TURN_2)
    elapsed = round(time.time() - t0, 1)

    types1, types2 = _event_types(ev1), _event_types(ev2)
    transcript = [{"turn": 1, "user": TURN_1, "events": [json.loads(e.json()) for e in ev1]},
                  {"turn": 2, "user": TURN_2, "events": [json.loads(e.json()) for e in ev2]}]

    from agent.system_prompt import build_system_prompt
    system_prompt = build_system_prompt(svc.agent)

    # Q1 — typed events out of the hermes stream
    q1 = {
        "question": "Does streaming expose enough structure for our typed SSE events?",
        "turn1_event_types": types1,
        "turn2_event_types": types2,
        "has_hypothesis": "hypothesis" in types1,
        "has_question": "question" in types1,
        "has_tool_call_and_result": "tool_call" in types1 and "tool_result" in types1,
        "has_diagnosis_by_turn2": "diagnosis" in types1 + types2,
        "elapsed_s": elapsed,
    }
    q1["pass"] = all([q1["has_hypothesis"], q1["has_question"],
                      q1["has_tool_call_and_result"]])

    # Q2 — skills/memory in library mode.
    # Skills are index-only in the prompt (bodies load on demand via skill_view).
    # Memory = config-gated file-based MemoryStore + the memory tool
    # (the _memory_manager attr is only for external plugin providers).
    q2 = {
        "question": "Do skills/memory work when driven purely as a library?",
        "skill_in_prompt_index": "al309-axial-play-check" in system_prompt,
        "memory_enabled": bool(getattr(svc.agent, "_memory_enabled", False)),
        "memory_store_active": getattr(svc.agent, "_memory_store", None) is not None,
        "memory_tool_exposed": "memory" in svc.exposed_tools,
        "skill_tools_exposed": [t for t in svc.exposed_tools if t.startswith("skill")],
        "hermes_home_state": sorted(str(p.relative_to(home)) for p in home.rglob("*")
                                    if p.is_file())[:40],
    }
    q2["pass"] = q2["skill_in_prompt_index"] and q2["memory_store_active"] \
        and q2["memory_tool_exposed"]

    # Q4 — trajectory export
    traj_file = home / "trajectory_samples.jsonl"
    q4 = {
        "question": "Can we export the session in hermes' trajectory format?",
        "trajectory_file": str(traj_file),
        "exists": traj_file.exists(),
    }
    if traj_file.exists():
        entries = [json.loads(line) for line in traj_file.read_text().splitlines() if line]
        q4["entries"] = len(entries)
        q4["sharegpt_format"] = all("conversations" in e for e in entries)
        q4["contains_tool_call"] = any("knowledge_retrieval" in json.dumps(e) for e in entries)
        q4["pass"] = q4["sharegpt_format"] and q4["contains_tool_call"]
    else:
        q4["pass"] = False

    return {"q1_streaming": q1, "q2_skills_memory": q2, "q4_trajectory": q4,
            "exposed_tools": svc.exposed_tools, "transcript": transcript}


# --- Q3: two parallel sessions, distinct HERMES_HOME, zero bleed ---

def run_worker(home: str, marker: str, api_key_env: str) -> None:
    home = Path(home)
    os.chdir(home)
    svc = _new_service(home, api_key_env)
    svc.start_session(f"tenant_{marker}")
    svc.handle_user_turn(
        f"Our machine is tagged {marker}. Controller SINUMERIK 840D shows AL 309, "
        f"rattling on the X-axis. What should I check first?")


def check_isolation() -> dict:
    homes, markers, keys = {}, ("TENANT-A-9931", "TENANT-B-4417"), \
        ("TWOGOOGLE_API_KEY", "NEW_GOOGLE_API_KEY")
    procs = []
    for name, marker, key_env in zip(("tenant_a", "tenant_b"), markers, keys):
        home = _fresh_home(name)
        homes[marker] = home
        procs.append(subprocess.Popen(
            [sys.executable, __file__, "--worker", "--home", str(home),
             "--marker", marker, "--key-env", key_env],
            cwd=_AGENTS_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True))
    outputs = [p.communicate()[0] for p in procs]

    def leaks(home: Path, foreign_marker: str) -> list[str]:
        hits = []
        for f in home.rglob("*"):
            if f.is_file():
                try:
                    if foreign_marker in f.read_text(errors="ignore"):
                        hits.append(str(f.relative_to(home)))
                except OSError:
                    pass
        return hits

    a, b = markers
    q3 = {
        "question": "Does per-HERMES_HOME isolation hold (parallel sessions, zero bleed)?",
        "worker_exit_codes": [p.returncode for p in procs],
        "marker_b_found_in_home_a": leaks(homes[a], b),
        "marker_a_found_in_home_b": leaks(homes[b], a),
        "own_marker_persisted_a": bool(leaks(homes[a], a)),
        "own_marker_persisted_b": bool(leaks(homes[b], b)),
    }
    q3["pass"] = (q3["worker_exit_codes"] == [0, 0]
                  and not q3["marker_b_found_in_home_a"]
                  and not q3["marker_a_found_in_home_b"])
    if any(p.returncode for p in procs):
        q3["worker_output_tail"] = [o[-1500:] for o in outputs]
    return q3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(_AGENTS_DIR / "spike_results.json"))
    ap.add_argument("--worker", action="store_true")
    ap.add_argument("--home")
    ap.add_argument("--marker")
    ap.add_argument("--key-env", default="GOOGLE_API_KEY")
    args = ap.parse_args()

    if args.worker:
        run_worker(args.home, args.marker, args.key_env)
        return 0

    results = run_main_session()
    results["q3_isolation"] = check_isolation()

    verdict = {k: results[k]["pass"] for k in
               ("q1_streaming", "q2_skills_memory", "q3_isolation", "q4_trajectory")}
    results["all_pass"] = all(verdict.values())
    Path(args.output).write_text(json.dumps(results, indent=2, ensure_ascii=False))

    print("\n" + "=" * 60)
    for k, ok in verdict.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {k}")
    print(f"\n  -> {'ALL FOUR PASS' if results['all_pass'] else 'NOT ALL PASS'}"
          f" — details in {args.output}")
    return 0 if results["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
