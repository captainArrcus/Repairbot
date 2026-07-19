"""Feature 2.5 — parent side of the embedded hermes agent.

Owns the worker process per session (spec D1), the tool RPC dispatch (spec D2
— domain tools run HERE, with DB/S3 access the worker never has), the single
allowlist enforcement point (spec D3, Techstack cross-cutting), and the
Pydantic validation/sanitization of everything the agent emits (spec D4).

agent_service drives `iter_turn_events` and persists; this module never
touches diagnostic_turn_events itself.
"""

import json
import queue
import shlex
import shutil
import subprocess
import threading
import time
from pathlib import Path

from pydantic import ValidationError

from app import config
from app.models.events import (
    DiagnosisEvent,
    DoneEvent,
    Event,
    GuidanceEvent,
    HypothesisEvent,
    QuestionEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from app.services import observability
from app.tools import vision_analysis, web_search
from app.tools.error_code_lookup import ErrorCodeLookup
from app.tools.knowledge_layer import KnowledgeRetrieval

# THE allowlist — 4 domain tools + hermes' 4 learning-loop tools (0.2 finding,
# ratified). Checked against the worker's ready handshake at every session start.
ALLOWED_TOOLS = frozenset(
    {
        "vision_analysis",
        "error_code_lookup",
        "knowledge_retrieval",
        "repair_web_search",
        "memory",
        "skills_list",
        "skill_view",
        "skill_manage",
    }
)

_EVENT_MODELS = {
    "thinking": ThinkingEvent,
    "hypothesis": HypothesisEvent,
    "question": QuestionEvent,
    "tool_call": ToolCallEvent,
    "tool_result": ToolResultEvent,
    "diagnosis": DiagnosisEvent,
    "guidance": GuidanceEvent,
    "done": DoneEvent,
}

_READY_TIMEOUT_S = 60


class AgentBusyError(Exception):
    """A turn for this session is already running (API maps to 409)."""


class Worker:
    """One hermes process per session; JSONL over stdio, reader thread + queue
    so turn reads can honor a deadline."""

    def __init__(self, session_id: str, tenant_id: str):
        self.session_id = session_id
        self.tenant_id = tenant_id
        self.lock = threading.Lock()
        self.turns_seen = 0
        tenant_dir = Path(config.HERMES_HOME_ROOT) / tenant_id
        # session-scoped CWD: hermes appends trajectories to the CWD (0.2 finding
        # #5), so this dir IS the session's trajectory — spec 2.7 D2
        work_dir = tenant_dir / "trajectories" / session_id
        work_dir.mkdir(parents=True, exist_ok=True)
        _sync_fleet_skills(tenant_dir)
        self.proc = subprocess.Popen(
            _worker_cmd(session_id, tenant_dir),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            env=None if config.AGENT_RUNNER == "docker" else _worker_env(session_id, tenant_dir),
            cwd=None if config.AGENT_RUNNER == "docker" else work_dir,
            text=True,
        )
        self._queue: queue.Queue = queue.Queue()
        threading.Thread(target=self._read_loop, daemon=True).start()
        ready = self.read_op(_READY_TIMEOUT_S)
        if ready.get("op") != "ready":
            self.kill()
            raise RuntimeError(f"worker failed to start: {ready}")
        if set(ready.get("tools") or []) != ALLOWED_TOOLS:
            self.kill()
            observability.log_agent_error(
                session_id, "allowlist_breach", f"worker exposes: {ready.get('tools')}"
            )
            raise RuntimeError(f"allowlist breach — worker exposes: {ready.get('tools')}")

    def _read_loop(self) -> None:
        for line in self.proc.stdout:
            self._queue.put(line)
        self._queue.put(None)  # EOF

    def send(self, op: dict) -> None:
        self.proc.stdin.write(json.dumps(op, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def read_op(self, timeout_s: float) -> dict:
        try:
            line = self._queue.get(timeout=timeout_s)
        except queue.Empty:
            raise TimeoutError(f"no worker output within {timeout_s}s") from None
        if line is None:
            raise RuntimeError("worker exited")
        return json.loads(line)

    def kill(self) -> None:
        self.proc.kill()
        self.proc.wait(timeout=10)

    @property
    def alive(self) -> bool:
        return self.proc.poll() is None


def _sync_fleet_skills(tenant_dir: Path) -> None:
    """Feature 2.7 (spec D7): promoted fleet skills reach the tenant at worker
    start. A tenant's own skill with the same name always wins."""
    fleet = Path(config.FLEET_SKILLS_DIR)
    if not fleet.is_dir():
        return
    for skill in fleet.iterdir():
        dest = tenant_dir / "skills" / skill.name
        if skill.is_dir() and not dest.exists():
            shutil.copytree(skill, dest)


def _worker_env(session_id: str, tenant_dir: Path) -> dict:
    import os

    return {
        **os.environ,
        "HERMES_HOME": str(tenant_dir),
        "REPAIR_SESSION_ID": session_id,
        "REPAIR_LLM_BASE_URL": config.REPAIR_LLM_BASE_URL,
        "REPAIR_LLM_MODEL": config.REPAIR_LLM_MODEL,
        "REPAIR_LLM_API_KEY": config.REPAIR_LLM_API_KEY or "",
        "REPAIR_LLM_FALLBACK_MODEL": config.REPAIR_LLM_FALLBACK_MODEL or "",
    }


def _worker_cmd(session_id: str, tenant_dir: Path) -> list[str]:
    if config.AGENT_RUNNER != "docker":
        return shlex.split(config.AGENT_WORKER_CMD)
    agents_dir = Path(__file__).resolve().parent.parent.parent / "agents"
    # egress-isolated worker (spec D8): internal network, proxy is the only way out
    return [
        "docker",
        "run",
        "-i",
        "--rm",
        "--network",
        config.AGENT_DOCKER_NETWORK,
        "-e",
        "HERMES_HOME=/hermes",
        "-e",
        f"REPAIR_SESSION_ID={session_id}",
        "-e",
        f"REPAIR_LLM_BASE_URL={config.REPAIR_LLM_BASE_URL}",
        "-e",
        f"REPAIR_LLM_MODEL={config.REPAIR_LLM_MODEL}",
        "-e",
        f"REPAIR_LLM_API_KEY={config.REPAIR_LLM_API_KEY or ''}",
        "-e",
        f"REPAIR_LLM_FALLBACK_MODEL={config.REPAIR_LLM_FALLBACK_MODEL or ''}",
        "-e",
        f"HTTPS_PROXY={config.AGENT_EGRESS_PROXY}",
        "-e",
        f"HTTP_PROXY={config.AGENT_EGRESS_PROXY}",
        "-v",
        f"{tenant_dir}:/hermes",
        "-v",
        f"{agents_dir}:/agents:ro",
        "-w",
        f"/hermes/trajectories/{session_id}",  # session trajectory dir (spec 2.7 D2)
        config.AGENT_DOCKER_IMAGE,
        "python",
        "/agents/hermes_worker.py",
    ]


# ponytail: unbounded worker registry, dies with the process; add an idle
# reaper when concurrent-session counts demand it
_workers: dict[str, Worker] = {}
_workers_guard = threading.Lock()


def acquire_worker(session_id: str, tenant_id: str) -> Worker:
    """Returns the session's worker with its turn lock held (release in caller).
    Raises AgentBusyError if a turn is already running."""
    with _workers_guard:
        worker = _workers.get(session_id)
        if worker is not None and not worker.alive:
            worker = None
        if worker is None:
            worker = Worker(session_id, tenant_id)
            _workers[session_id] = worker
    if not worker.lock.acquire(blocking=False):
        raise AgentBusyError(session_id)
    return worker


def drop_worker(session_id: str) -> None:
    with _workers_guard:
        worker = _workers.pop(session_id, None)
    if worker is not None:
        worker.kill()


def iter_turn_events(
    cur,
    worker: Worker,
    turn_op: dict,
    session_media: set[str],
    agent_turn_index: int,
    tools_called: list[dict],
):
    """Drive one worker turn; yields validated Events as they happen.

    Domain-tool RPCs execute here (parent venv, DB cursor of the turn) and are
    surfaced as tool_call/tool_result events at RPC time. The caller enforces
    the safety gate and the trailing done event.
    """
    session_id = worker.session_id
    deadline = time.monotonic() + config.AGENT_TURN_TIMEOUT_S
    try:
        worker.send(turn_op)
    except (BrokenPipeError, OSError) as exc:
        yield from _worker_failed(session_id, f"worker unreachable: {exc}")
        return

    while True:
        try:
            op = worker.read_op(max(0.0, deadline - time.monotonic()))
        except (TimeoutError, RuntimeError, ValueError) as exc:
            worker.kill()
            yield from _worker_failed(session_id, str(exc))
            return

        kind = op.get("op")
        if kind == "done":
            return
        if kind == "tool":
            tool, args = op.get("tool", "?"), op.get("args") or {}
            yield ToolCallEvent(tool=tool, args=args)
            result, summary = _dispatch_tool(cur, tool, args, session_media)
            yield ToolResultEvent(
                tool=tool,
                result_summary=summary,
                raw_result=result if isinstance(result, dict) else None,
            )
            tools_called.append({"tool": tool, "args": args, "result_summary": summary})
            try:
                worker.send(
                    {
                        "op": "tool_result",
                        "id": op.get("id"),
                        "result": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )
            except (BrokenPipeError, OSError) as exc:
                yield from _worker_failed(session_id, f"worker unreachable: {exc}")
                return
        elif kind == "event":
            yield build_event(
                session_id, op.get("etype", "?"), op.get("data") or {}, agent_turn_index
            )
        elif kind in ("error", "fatal"):
            if kind == "fatal":
                worker.kill()
            observability.log_agent_error(session_id, "worker_error", op.get("detail", ""))
            yield ThinkingEvent(
                content="Der Diagnose-Agent hat einen Fehler gemeldet — "
                "bitte senden Sie Ihre Nachricht erneut."
            )
            return
        else:
            observability.log_agent_error(session_id, "worker_error", f"unknown op: {op}")


def _worker_failed(session_id: str, detail: str):
    observability.log_agent_error(session_id, "worker_error", detail)
    yield ThinkingEvent(
        content="Der Diagnose-Agent ist gerade nicht erreichbar — "
        "bitte senden Sie Ihre Nachricht erneut."
    )


def build_event(session_id: str, etype: str, data: dict, agent_turn_index: int) -> Event:
    """Validation authority (spec D4): worker output -> typed event, or a
    sanitized thinking event + Langfuse error. Raw output is never forwarded."""
    model = _EVENT_MODELS.get(etype)
    if model is not None:
        payload = {k: v for k, v in data.items() if k != "id"}
        if model is HypothesisEvent:
            payload.setdefault("introduced_at_turn", agent_turn_index)
        try:
            return model(**payload)
        except ValidationError as exc:
            observability.log_agent_error(
                session_id,
                "invalid_event",
                f"{etype}: {exc.errors()[:3]} data={json.dumps(data, default=str)[:300]}",
            )
    elif etype != "raw":
        observability.log_agent_error(session_id, "invalid_event", f"unknown type {etype!r}")
    content = str(data.get("content") or json.dumps(data, ensure_ascii=False, default=str))[:500]
    return ThinkingEvent(content=content)


def _dispatch_tool(
    cur, tool: str, args: dict, session_media: set[str]
) -> tuple[dict | list | None, str]:
    """Execute a domain tool for the agent. Returns (result, summary). Failures
    become an error payload + failure summary — never a crashed turn."""
    try:
        if tool == "vision_analysis":
            key = args.get("media_key", "")
            if key not in session_media:
                # trust boundary: the agent only sees media uploaded in THIS session
                raise PermissionError(f"media_key {key!r} does not belong to this session")
            result = vision_analysis.analyze(key)
            summary = (
                f"controller: {result['detected_controller'] or 'unbekannt'}, "
                f"codes: {', '.join(result['detected_codes']) or 'keine'}"
            )
        elif tool == "error_code_lookup":
            lookup = ErrorCodeLookup(cur.connection)
            # family variants (SINUMERIK vs SINUMERIK_840D_sl) are canonicalized
            # inside the tool (2.8) — no family=None retry needed
            result = lookup.lookup(args.get("controller_family"), args.get("code", ""))
            summary = (
                f"exact match: {result['code']} ({result['controller_family']})"
                if result
                else "no exact match in error_codes"
            )
        elif tool == "knowledge_retrieval":
            rows = KnowledgeRetrieval(cur.connection).search_semantic(
                args.get("query", ""), top_k=5
            )
            result = {"results": rows}
            summary = (
                f"{len(rows)} candidate alarms: {', '.join(r['code'] for r in rows) or 'none'}"
            )
        elif tool == "repair_web_search":
            hits = web_search.search(args.get("query", ""))
            result = {"results": hits}
            summary = f"{len(hits)} web results"
        else:
            raise PermissionError(f"tool {tool!r} is not allowlisted")
        return result, summary
    except Exception as exc:
        return {"error": str(exc)}, f"{tool} failed: {exc}"
