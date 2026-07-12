"""Feature 0.2 — interactive CLI diagnostic agent (hermes embed spike).

Usage (inside .venv-hermes):
    python run_cli.py

Every typed step event is printed and appended to agents/logs/session_<id>.jsonl.
"""
import sys
import uuid
from pathlib import Path

from hermes_service import HermesAgentService, StepEvent

_ICONS = {"thinking": "…", "hypothesis": "◆", "question": "?", "tool_call": "⚙",
          "tool_result": "⇒", "diagnosis": "✓", "guidance": "→", "done": "■"}


def main():
    session_id = f"cli_{uuid.uuid4().hex[:8]}"
    log_path = Path(__file__).parent / "logs" / f"session_{session_id}.jsonl"
    log_path.parent.mkdir(exist_ok=True)
    log = open(log_path, "a", encoding="utf-8")

    def print_event(ev: StepEvent):
        line = ev.json()
        print(f"  {_ICONS.get(ev.type, ' ')} [{ev.type}] {line}")
        log.write(line + "\n")
        log.flush()

    service = HermesAgentService(on_event=print_event)
    service.start_session(session_id)

    print(f"RepairRöpi CLI — session {session_id}")
    print(f"model={service.model}  tools={service.exposed_tools}")
    print(f"log: {log_path}")
    print('Describe the fault (e.g. "Controller: SINUMERIK 840D, AL 309. '
          'Rattling when jogging X."). Ctrl-D to exit.\n')

    while True:
        try:
            text = input("technician> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            break
        if not text:
            continue
        service.handle_user_turn(text)
        print()


if __name__ == "__main__":
    sys.exit(main())
