"""Deterministic worker stub speaking the 2.5 stdio protocol (tests only).

Stands in for agents/hermes_worker.py so the parent-side pipeline (RPC
dispatch, validation, safety gate, tenant homes) is testable without the
hermes venv or an LLM. Behavior knobs via STUB_MODE env:
normal | invalid | safety | badtools | sleep | marker
"""

import json
import os
import sys
import time

_rpc_id = 0


def emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def read() -> dict | None:
    line = sys.stdin.readline()
    return json.loads(line) if line else None


def rpc(tool: str, args: dict) -> str:
    global _rpc_id
    _rpc_id += 1
    emit({"op": "tool", "id": _rpc_id, "tool": tool, "args": args})
    reply = read()
    return reply["result"]


def run_turn(mode: str, op: dict) -> None:
    if mode == "sleep":
        time.sleep(30)
        emit({"op": "done"})
        return
    if mode == "marker":
        home = os.environ["HERMES_HOME"]
        with open(os.path.join(home, "marker.txt"), "a") as f:
            f.write(op["text"] + "\n")
        time.sleep(0.3)  # keep the two parallel tenant turns overlapping
        emit({"op": "event", "etype": "thinking", "data": {"content": f"home={home}"}})
        emit({"op": "event", "etype": "done", "data": {"status": "awaiting_user_input"}})
        emit({"op": "done"})
        return
    if mode == "invalid":
        emit({"op": "event", "etype": "hypothesis", "data": {"description": "fields missing"}})
        emit({"op": "event", "etype": "frobnicate", "data": {"content": "unknown type"}})
        emit({"op": "event", "etype": "raw", "data": {"content": "prose the model leaked"}})
        emit({"op": "done"})
        return
    if mode == "safety":
        emit(
            {
                "op": "event",
                "etype": "guidance",
                "data": {
                    "step_index": 1,
                    "safety_level": "high",
                    "content": "Schaltschrank öffnen — vorher Hauptschalter aus (LOTO).",
                },
            }
        )
        emit(
            {
                "op": "event",
                "etype": "guidance",
                "data": {"step_index": 2, "safety_level": "low", "content": "Klemme X3 prüfen."},
            }
        )
        emit(
            {
                "op": "event",
                "etype": "question",
                "data": {"content": "Was sehen Sie?", "evidence_type": "text"},
            }
        )
        emit({"op": "event", "etype": "done", "data": {"status": "complete"}})
        emit({"op": "done"})
        return

    # normal: exercise RPC against the real parent-side tools
    if op.get("context"):
        emit(
            {
                "op": "event",
                "etype": "thinking",
                "data": {"content": "context:" + op["context"][:200]},
            }
        )
    for m in op.get("media") or []:
        rpc("vision_analysis", {"media_key": m["key"]})
    if os.environ.get("STUB_EXTRA_VISION_KEY"):
        rpc("vision_analysis", {"media_key": os.environ["STUB_EXTRA_VISION_KEY"]})
    alarm = json.loads(rpc("error_code_lookup", {"code": "AL 309"}))
    causes = (alarm or {}).get("probable_causes") or ["unbekannte Ursache"]
    emit({"op": "event", "etype": "thinking", "data": {"content": "Analysiere AL 309 ..."}})
    emit(
        {
            "op": "event",
            "etype": "hypothesis",
            "data": {"hypothesis_id": "h1", "description": str(causes[0]), "confidence": 0.55},
        }
    )
    emit(
        {
            "op": "event",
            "etype": "question",
            "data": {
                "content": "Wie viel Axialspiel in mm?",
                "evidence_type": "numeric",
                "required_format": "mm",
            },
        }
    )
    emit({"op": "event", "etype": "done", "data": {"status": "awaiting_user_input"}})
    emit({"op": "done"})


def main() -> None:
    mode = os.environ.get("STUB_MODE", "normal")
    tools = [
        "vision_analysis",
        "error_code_lookup",
        "knowledge_retrieval",
        "repair_web_search",
        "memory",
        "skills_list",
        "skill_view",
        "skill_manage",
    ]
    if mode == "badtools":
        tools.append("terminal_execute")
    emit({"op": "ready", "tools": tools})
    while True:
        op = read()
        if op is None or op.get("op") == "exit":
            break
        if op.get("op") == "turn":
            run_turn(mode, op)


if __name__ == "__main__":
    main()
