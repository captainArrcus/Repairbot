"""Feature 2.5 — hermes agent worker (runs in .venv-hermes, one process per session).

Speaks newline-delimited JSON with app/services/hermes_backend.py over
stdin/stdout (spec D1). Domain tools are RPC-proxied to the parent (spec D2):
the handler writes a `tool` op and blocks until the parent replies — this
process holds no DB/S3 credentials and needs egress only to the LLM endpoint.

Protocol (one JSON object per line):
  worker -> parent: {"op":"ready","tools":[...]}
                    {"op":"event","etype":"<type>","data":{...}}   (post-turn)
                    {"op":"tool","id":n,"tool":"...","args":{...}} (blocks)
                    {"op":"done"} | {"op":"error","detail":"..."} | {"op":"fatal",...}
  parent -> worker: {"op":"turn","text":"...","media":[{"key","content_type"}],"context":"..."}
                    {"op":"tool_result","id":n,"result":"<json string>"}
"""

import json
import os
import sys
from pathlib import Path

# hermes prints banners/progress; keep the protocol channel clean by keeping a
# private handle to real stdout and pointing sys.stdout at stderr (spike ran
# quiet_mode but one stray print would corrupt the JSONL stream)
_PROTO = os.fdopen(os.dup(1), "w")
sys.stdout = sys.stderr

DOMAIN_TOOLS = {
    "vision_analysis": {
        "description": (
            "Analyze an uploaded photo (control panel, component, damage): OCR any "
            "displayed error codes and detect the controller brand. Call this on every "
            "new photo media_key before hypothesizing."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "media_key": {"type": "string", "description": "media_key of an uploaded image"}
            },
            "required": ["media_key"],
        },
    },
    "error_code_lookup": {
        "description": (
            "Exact lookup of a CNC error/alarm code (SINUMERIK/Heidenhain/Fanuc). "
            "Handles format variants (al-309, AL309, 309). Returns the full alarm "
            "record (causes, actions, discriminating questions) or null."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "error code as seen/heard"},
                "controller_family": {
                    "type": "string",
                    "description": "optional controller family filter",
                },
            },
            "required": ["code"],
        },
    },
    "knowledge_retrieval": {
        "description": (
            "Semantic search over the CNC knowledge base for symptom descriptions "
            "without a known code. Returns narrowed candidate alarms to reason over."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "symptom description"}},
            "required": ["query"],
        },
    },
    "repair_web_search": {
        "description": (
            "Web search fallback for error codes, symptoms or part numbers not in the "
            "knowledge base. Use only after error_code_lookup/knowledge_retrieval fail."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
}

LEARNING_TOOLS = {"memory", "skills_list", "skill_view", "skill_manage"}
ALLOWED_TOOLS = set(DOMAIN_TOOLS) | LEARNING_TOOLS

DIAGNOSTIC_PROTOCOL = """
# RepairRöpi Diagnostic Protocol

You are a senior CNC machine diagnostic partner (SINUMERIK, Heidenhain, Fanuc).
You investigate faults collaboratively: form ranked hypotheses, ask ONE targeted
discriminating question per turn, narrow down until confident, then diagnose.
Reply in the technician's language (German or English).

Tool policy:
- New photo media_key in the user message -> call vision_analysis FIRST.
- Any error code (seen, typed or heard) -> error_code_lookup. Trust an exact hit.
- Symptom without a usable code -> knowledge_retrieval; reason ONLY over its candidates.
- Nothing found anywhere -> repair_web_search, and say the knowledge base had no match.

## Output format (STRICT)
After tool use, your entire visible reply MUST be a sequence of lines, each line
exactly one JSON object, no markdown fences, no prose outside JSON:

{"type": "thinking", "content": "<short reasoning summary>"}
{"type": "hypothesis", "hypothesis_id": "h1", "description": "...", "confidence": 0.55, "eliminated": false}
{"type": "question", "content": "...", "evidence_type": "photo|audio|tactile|numeric|text", "required_format": "e.g. mm"}
{"type": "diagnosis", "hypothesis_id": "h1", "confidence": 0.9, "explanation": "..."}
{"type": "guidance", "step_index": 1, "content": "...", "safety_level": "low|medium|high"}
{"type": "done", "status": "awaiting_user_input|awaiting_verification|complete"}

Rules:
- Re-emit the full current hypothesis list each turn (updated confidences;
  eliminated ones with "eliminated": true).
- Emit "question" only while evidence is still needed; emit "diagnosis" +
  "guidance" once confident (>= 0.8).
- SAFETY: after a guidance step with safety_level "high" (electrical work,
  lockout/tagout, moving axes), emit "done" immediately and wait for the
  technician to explicitly confirm completion before ANY further step.
- The LAST line of every reply is a "done" object.
""".strip()

_KNOWN_EVENT_TYPES = {"thinking", "hypothesis", "question", "diagnosis", "guidance", "done"}

_rpc_counter = 0


def _emit(obj: dict) -> None:
    _PROTO.write(json.dumps(obj, ensure_ascii=False) + "\n")
    _PROTO.flush()


def _read_op() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line)


def _rpc_tool_call(tool: str, args: dict) -> str:
    global _rpc_counter
    _rpc_counter += 1
    call_id = _rpc_counter
    _emit({"op": "tool", "id": call_id, "tool": tool, "args": args})
    reply = _read_op()
    if reply is None or reply.get("op") != "tool_result" or reply.get("id") != call_id:
        raise RuntimeError(f"tool RPC protocol violation: {reply!r}")
    return reply["result"]


def _build_agent(session_id: str):
    home = Path(os.environ["HERMES_HOME"])
    home.mkdir(parents=True, exist_ok=True)
    cfg = home / "config.yaml"
    if not cfg.exists():
        # built-in memory is config-gated per tenant home (0.2 spike finding #3)
        cfg.write_text("memory:\n  memory_enabled: true\n  user_profile_enabled: true\n")

    import model_tools
    import toolsets
    from run_agent import AIAgent
    from tools.registry import registry

    for name, schema in DOMAIN_TOOLS.items():
        if registry.get_entry(name) is None:
            registry.register(
                name=name,
                toolset="repair_domain",
                schema={"name": name, **schema},
                handler=lambda args, _n=name, **kw: _rpc_tool_call(_n, args or {}),
                emoji="🔧",
            )
    toolsets.create_custom_toolset(
        "repair_domain",
        "CNC diagnosis domain tools (RPC-proxied to AgentService)",
        tools=list(DOMAIN_TOOLS),
    )

    allowed_toolsets = ["repair_domain", "skills", "memory"]
    agent = AIAgent(
        base_url=os.environ["REPAIR_LLM_BASE_URL"],
        api_key=os.environ["REPAIR_LLM_API_KEY"],
        model=os.environ["REPAIR_LLM_MODEL"],
        fallback_model=os.environ.get("REPAIR_LLM_FALLBACK_MODEL") or None,
        session_id=session_id,
        enabled_toolsets=allowed_toolsets,
        ephemeral_system_prompt=DIAGNOSTIC_PROTOCOL,
        save_trajectories=True,
        quiet_mode=True,
        skip_context_files=True,
        max_iterations=12,
    )

    defs = model_tools.get_tool_definitions(enabled_toolsets=allowed_toolsets, quiet_mode=True)
    exposed = sorted(d["function"]["name"] for d in defs)
    if set(exposed) != ALLOWED_TOOLS:
        raise RuntimeError(f"allowlist mismatch — exposed: {exposed}")
    return agent, exposed


def _map_new_messages(messages: list) -> None:
    """Post-turn mapping (0.2 spike): protocol NDJSON -> event ops. Domain tool
    calls are skipped — the parent already synthesized their events at RPC time;
    learning-tool activity is surfaced from the message history."""
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role == "assistant":
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function", {})
                name = fn.get("name", "?")
                if name in DOMAIN_TOOLS:
                    continue
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {"_raw": str(fn.get("arguments"))[:200]}
                _emit({"op": "event", "etype": "tool_call", "data": {"tool": name, "args": args}})
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                _emit_protocol_lines(content)
        elif role == "tool" and msg.get("name") not in DOMAIN_TOOLS:
            _emit(
                {
                    "op": "event",
                    "etype": "tool_result",
                    "data": {
                        "tool": msg.get("name", "?"),
                        "result_summary": str(msg.get("content", ""))[:300],
                    },
                }
            )


def _emit_protocol_lines(text: str) -> None:
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("```"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            obj = None
        if isinstance(obj, dict) and obj.get("type") in _KNOWN_EVENT_TYPES:
            etype = obj.pop("type")
            _emit({"op": "event", "etype": etype, "data": obj})
        else:
            # raw prose / malformed line — parent sanitizes + logs (spec D4)
            _emit({"op": "event", "etype": "raw", "data": {"content": line[:500]}})


def _format_turn(op: dict) -> str:
    text = op.get("text") or ""
    if op.get("context"):
        text = f"{op['context']}\n\n{text}"
    media = op.get("media") or []
    if media:
        lines = "\n".join(f"- media_key={m['key']} ({m.get('content_type', '?')})" for m in media)
        text = f"{text}\n\n[Angehängte Medien]\n{lines}"
    return text


def main() -> None:
    session_id = os.environ.get("REPAIR_SESSION_ID", "dev-session")
    try:
        agent, exposed = _build_agent(session_id)
    except Exception as exc:
        _emit({"op": "fatal", "detail": str(exc)[:500]})
        sys.exit(1)
    _emit({"op": "ready", "tools": exposed})

    history = None
    while True:
        try:
            op = _read_op()
        except ValueError as exc:
            _emit({"op": "error", "detail": f"bad input line: {exc}"})
            continue
        if op is None or op.get("op") == "exit":
            break
        if op.get("op") != "turn":
            _emit({"op": "error", "detail": f"unexpected op: {op.get('op')}"})
            continue
        try:
            result = agent.run_conversation(_format_turn(op), conversation_history=history)
            messages = result.get("messages") or result.get("conversation_history") or []
            prev_len = len(history) if history else 0
            history = messages
            _map_new_messages(messages[prev_len:])
            _emit({"op": "done"})
        except Exception as exc:
            _emit({"op": "error", "detail": str(exc)[:500]})


if __name__ == "__main__":
    main()
