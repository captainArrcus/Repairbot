"""Feature 0.2 — hermes embed spike.

Embeds run_agent.AIAgent (NousResearch/hermes-agent, pinned commit 4281151)
behind HermesAgentService. Exactly ONE domain tool is registered:
knowledge_retrieval — the structured spine of the Feature 0.1 hybrid winner.
The embedded agent itself is the "LLM over narrowed candidates" half.

Run inside .venv-hermes (see agents/requirements_agents.txt).
"""
import json
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_AGENTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _AGENTS_DIR.parent.parent
load_dotenv(_AGENTS_DIR.parent / ".env")

sys.path.insert(0, str(_AGENTS_DIR.parent / "knowledge_spike"))
import spike_a_structured as spike_a  # noqa: E402
from corpus_loader import load_full_corpus, alarm_to_text, fault_pattern_to_text  # noqa: E402

DEFAULT_BASE_URL = os.getenv(
    "REPAIR_LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
)
DEFAULT_MODEL = os.getenv("REPAIR_LLM_MODEL", "gemini-3.1-flash-lite")

DIAGNOSTIC_PROTOCOL = """
# RepairRöpi Diagnostic Protocol

You are a senior CNC machine diagnostic partner (SINUMERIK, Heidenhain, Fanuc).
You investigate faults collaboratively: form ranked hypotheses, ask ONE targeted
discriminating question per turn, narrow down until confident, then diagnose.
Reply in the technician's language (German or English).

On every new symptom or error code, call the knowledge_retrieval tool FIRST.
If it returns path "exact", trust it. If it returns "narrowed_candidates",
reason over those candidates only.

## Output format (STRICT)
After any tool use, your entire visible reply MUST be a sequence of lines,
each line exactly one JSON object, no markdown fences, no prose outside JSON:

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
- The LAST line of every reply is a "done" object.
""".strip()

# Event types we accept from the model, with their required fields.
_REQUIRED_FIELDS = {
    "thinking": ("content",),
    "hypothesis": ("hypothesis_id", "description", "confidence"),
    "question": ("content", "evidence_type"),
    "diagnosis": ("hypothesis_id", "confidence", "explanation"),
    "guidance": ("step_index", "content"),
    "done": ("status",),
}
_FORBIDDEN_TOOL_MARKERS = ("terminal", "browser", "execute", "shell", "delegate", "spawn")


@dataclass
class StepEvent:
    type: str
    data: dict

    def json(self) -> str:
        return json.dumps({"id": str(uuid.uuid4()), "type": self.type, **self.data},
                          ensure_ascii=False)


# --- knowledge tool (structured spine of the 0.1 hybrid winner) ---

_corpus = None


def _get_corpus():
    global _corpus
    if _corpus is None:
        _corpus = load_full_corpus(str(_REPO_ROOT / "Research_Data"))
    return _corpus


def knowledge_retrieval(query: str) -> str:
    """Exact error-code lookup fast-path; else top-5 narrowed candidates."""
    corpus = _get_corpus()
    code = spike_a._extract_error_code(query)
    if code:
        exact = spike_a._exact_code_match(code, corpus)
        if exact:
            return json.dumps({
                "path": "exact",
                "results": [{
                    "code": a.code,
                    "controller_family": a.controller_family,
                    "message": a.message_en,
                    "probable_causes": a.probable_causes,
                    "recommended_actions": a.recommended_actions,
                    "related_components": a.related_components,
                    "manual_reference": a.manual_reference,
                    "confidence": conf,
                } for a, conf in exact[:3]],
            }, ensure_ascii=False)

    hits = spike_a._tfidf_search(query, corpus, top_k=5)
    candidates = [
        alarm_to_text(src) if hasattr(src, "code") else fault_pattern_to_text(src)
        for src, _score in hits
    ]
    return json.dumps({"path": "narrowed_candidates", "candidates": candidates},
                      ensure_ascii=False)


# Bare function schema — tools/registry.py wraps it in the OpenAI envelope itself.
KNOWLEDGE_TOOL_SCHEMA = {
    "name": "knowledge_retrieval",
    "description": (
        "Search the CNC knowledge base (SINUMERIK/Heidenhain/Fanuc alarms + "
        "mechanical fault patterns). Pass the error code and/or symptom text. "
        "Returns either an exact alarm record or narrowed candidate faults."
    ),
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string",
                                  "description": "Error code and/or symptom description"}},
        "required": ["query"],
    },
}


class HermesAgentService:
    """Thin wrapper — the FastAPI layer (Feature 1.3) talks to this, never to hermes."""

    def __init__(self, base_url: str = None, api_key: str = None, model: str = None,
                 hermes_home: str = None, on_event=None):
        self.base_url = base_url or DEFAULT_BASE_URL
        self.api_key = api_key or os.getenv("REPAIR_LLM_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model = model or DEFAULT_MODEL
        self.hermes_home = str(hermes_home or _AGENTS_DIR / ".hermes_home" / "default")
        self.on_event = on_event
        self.agent = None
        self.exposed_tools: list[str] = []
        self._history = None

    # --- lifecycle ---

    def start_session(self, session_id: str) -> None:
        # HERMES_HOME must be tenant-scoped before hermes modules read it.
        os.environ["HERMES_HOME"] = self.hermes_home
        home = Path(self.hermes_home)
        home.mkdir(parents=True, exist_ok=True)
        # Built-in memory is config-gated (agent_init reads memory.memory_enabled,
        # default False) — enable it per tenant home.
        cfg = home / "config.yaml"
        if not cfg.exists():
            cfg.write_text("memory:\n  memory_enabled: true\n  user_profile_enabled: true\n")

        from tools.registry import registry
        import toolsets
        from run_agent import AIAgent
        import model_tools

        if registry.get_entry("knowledge_retrieval") is None:
            registry.register(
                name="knowledge_retrieval",
                toolset="repair_knowledge",
                schema=KNOWLEDGE_TOOL_SCHEMA,
                handler=lambda args, **kw: knowledge_retrieval(args.get("query", "")),
                emoji="🔧",
            )
            toolsets.create_custom_toolset(
                "repair_knowledge", "CNC diagnosis knowledge layer (Feature 0.1 hybrid)",
                tools=["knowledge_retrieval"],
            )

        # Allowlist = our domain tool + hermes' learning-loop tools. The skills
        # index/memory only function through their own tools (system_prompt.py
        # gates on skills_list/skill_view being valid tools) — spike finding,
        # see FINDINGS.md. Still no terminal/browser/code-exec/delegation.
        allowed_toolsets = ["repair_knowledge", "skills", "memory"]
        self.agent = AIAgent(
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            session_id=session_id,
            enabled_toolsets=allowed_toolsets,
            ephemeral_system_prompt=DIAGNOSTIC_PROTOCOL,
            save_trajectories=True,
            quiet_mode=True,
            skip_context_files=True,
            max_iterations=12,
        )

        defs = model_tools.get_tool_definitions(
            enabled_toolsets=allowed_toolsets, quiet_mode=True)
        self.exposed_tools = sorted(d["function"]["name"] for d in defs)
        assert "knowledge_retrieval" in self.exposed_tools, "domain tool not exposed"
        leaked = [n for n in self.exposed_tools
                  if any(m in n.lower() for m in _FORBIDDEN_TOOL_MARKERS)]
        assert not leaked, f"allowlist breach — forbidden tools exposed: {leaked}"

    # --- turns ---

    def handle_user_turn(self, text: str, media_paths: list[str] = None) -> list[StepEvent]:
        assert self.agent is not None, "call start_session first"
        if media_paths:
            raise NotImplementedError("media handling lands in Features 2.3/2.4")

        result = self.agent.run_conversation(text, conversation_history=self._history)
        messages = result.get("messages") or result.get("conversation_history") or []
        prev_len = len(self._history) if self._history else 0
        self._history = messages

        events = self._map_messages(messages[prev_len:])
        for ev in events:
            if self.on_event:
                self.on_event(ev)
        return events

    # --- hermes messages -> typed events ---

    def _map_messages(self, messages: list) -> list[StepEvent]:
        events = []
        for msg in messages:
            role = msg.get("role") if isinstance(msg, dict) else None
            if role == "assistant":
                for tc in msg.get("tool_calls") or []:
                    fn = tc.get("function", {})
                    try:
                        args = json.loads(fn.get("arguments") or "{}")
                    except ValueError:
                        args = {"_raw": str(fn.get("arguments"))[:200]}
                    events.append(StepEvent("tool_call", {"tool": fn.get("name", "?"),
                                                          "args": args}))
                content = msg.get("content")
                if isinstance(content, str) and content.strip():
                    events.extend(self._parse_protocol_text(content))
            elif role == "tool":
                summary = str(msg.get("content", ""))[:300]
                events.append(StepEvent("tool_result", {"tool": msg.get("name", "?"),
                                                        "result_summary": summary}))
        return events

    def _parse_protocol_text(self, text: str) -> list[StepEvent]:
        events = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("```"):
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                obj = None
            if isinstance(obj, dict) and obj.get("type") in _REQUIRED_FIELDS:
                etype = obj.pop("type")
                missing = [f for f in _REQUIRED_FIELDS[etype] if f not in obj]
                if not missing:
                    events.append(StepEvent(etype, obj))
                    continue
                print(f"[hermes_service] invalid {etype} event, missing {missing} — sanitized",
                      file=sys.stderr)
            # Prose / invalid output is never forwarded raw (Feature 2.5 rule).
            events.append(StepEvent("thinking", {"content": line[:500]}))
        return events


if __name__ == "__main__":
    # ponytail: self-check — the knowledge tool works without any LLM or hermes install.
    r = json.loads(knowledge_retrieval("SINUMERIK 840D AL 309, rattling when jogging X"))
    assert r["path"] in ("exact", "narrowed_candidates"), r
    payload = r.get("results") or r.get("candidates")
    assert payload, "knowledge_retrieval returned nothing"
    print(f"knowledge_retrieval OK — path={r['path']}, {len(payload)} result(s)")
    print(json.dumps(payload[0], ensure_ascii=False)[:300])
