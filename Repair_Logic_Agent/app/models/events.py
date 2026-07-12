"""Feature 1.3 — typed SSE event schemas.

Canonical Roadmap section "Exact SSE event schema" implemented verbatim; the
class ClassVar `type` is the SSE event name (`event:` header), the payload `id`
is a per-event UUID. The wire-level monotonic id is `{turn_index}.{event_index}`
and lives in the SSE framing, not here (spec 1.3 D4).
"""

from typing import ClassVar, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _event_id() -> str:
    return str(uuid4())


class ThinkingEvent(BaseModel):
    type: ClassVar[str] = "thinking"
    id: str = Field(default_factory=_event_id)
    content: str


class HypothesisEvent(BaseModel):
    type: ClassVar[str] = "hypothesis"
    id: str = Field(default_factory=_event_id)
    hypothesis_id: str
    description: str
    confidence: float = Field(ge=0, le=1)
    introduced_at_turn: int
    eliminated: bool | None = None


class QuestionEvent(BaseModel):
    type: ClassVar[str] = "question"
    id: str = Field(default_factory=_event_id)
    content: str
    evidence_type: Literal["photo", "audio", "tactile", "numeric", "text"]
    required_format: str | None = None


class ToolCallEvent(BaseModel):
    type: ClassVar[str] = "tool_call"
    id: str = Field(default_factory=_event_id)
    tool: str
    args: dict


class ToolResultEvent(BaseModel):
    type: ClassVar[str] = "tool_result"
    id: str = Field(default_factory=_event_id)
    tool: str
    result_summary: str
    raw_result: dict | None = None


class DiagnosisEvent(BaseModel):
    type: ClassVar[str] = "diagnosis"
    id: str = Field(default_factory=_event_id)
    hypothesis_id: str
    confidence: float = Field(ge=0, le=1)
    explanation: str


class GuidanceEvent(BaseModel):
    type: ClassVar[str] = "guidance"
    id: str = Field(default_factory=_event_id)
    step_index: int
    content: str
    # required, no default: gates the physical-safety approval flow (Techstack guardrail 4)
    safety_level: Literal["low", "medium", "high"]


class DoneEvent(BaseModel):
    type: ClassVar[str] = "done"
    id: str = Field(default_factory=_event_id)
    status: Literal["awaiting_user_input", "awaiting_verification", "complete"]


Event = (
    ThinkingEvent
    | HypothesisEvent
    | QuestionEvent
    | ToolCallEvent
    | ToolResultEvent
    | DiagnosisEvent
    | GuidanceEvent
    | DoneEvent
)
