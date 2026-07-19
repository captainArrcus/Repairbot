// Feature 2.6 — pure reducer over the canonical SSE events (Roadmap schema).
// The stream endpoint replays the whole session on fresh connect; the
// monotonic wire-id filter makes replays and reconnects idempotent.

export type Hypothesis = {
  hypothesis_id: string;
  description: string;
  confidence: number;
  eliminated?: boolean;
};

export type Question = {
  content: string;
  evidence_type: "photo" | "audio" | "tactile" | "numeric" | "text";
  required_format?: string | null;
};

export type Guidance = {
  step_index: number;
  content: string;
  safety_level: "low" | "medium" | "high";
};

export type Diagnosis = {
  hypothesis_id: string;
  confidence: number;
  explanation: string;
};

export type LogEntry = { key: string; sortKey: number; text: string };

export type SessionView = {
  hypotheses: Hypothesis[];
  question: Question | null;
  guidance: Guidance[];
  diagnosis: Diagnosis | null;
  thinking: string;
  doneStatus: string | null;
  busy: boolean;
  log: LogEntry[];
  lastEventId: string | null; // wire id "<turn_index>.<event_index>"
  lastTurnIndex: number;
};

export function emptyView(): SessionView {
  return {
    hypotheses: [],
    question: null,
    guidance: [],
    diagnosis: null,
    thinking: "",
    doneStatus: null,
    busy: false,
    log: [],
    lastEventId: null,
    lastTurnIndex: 0,
  };
}

function parseWireId(id: string | null | undefined): [number, number] | null {
  if (!id) return null;
  const [t, e] = id.split(".");
  const ti = Number(t);
  const ei = Number(e);
  return Number.isFinite(ti) && Number.isFinite(ei) ? [ti, ei] : null;
}

function isStale(view: SessionView, wireId: string | null | undefined): boolean {
  const next = parseWireId(wireId);
  if (!next) return false; // no id → cannot order, let it through
  const last = parseWireId(view.lastEventId);
  if (!last) return false;
  return next[0] < last[0] || (next[0] === last[0] && next[1] <= last[1]);
}

function withLog(view: SessionView, text: string, sortKey: number, key: string): SessionView {
  if (view.log.some((l) => l.key === key)) return view;
  return { ...view, log: [...view.log, { key, sortKey, text }].sort((a, b) => a.sortKey - b.sortKey) };
}

// Agent events sort by wire position; a user turn precedes the agent turn that
// answers it, so it slots at lastTurnIndex + 0.5 (turn indexes alternate user/agent).
function agentSortKey(wireId: string | null | undefined, view: SessionView): number {
  const parsed = parseWireId(wireId);
  return parsed ? parsed[0] * 1000 + parsed[1] : (view.lastTurnIndex + 1) * 1000;
}

export function applyEvent(
  view: SessionView,
  type: string,
  data: any,
  wireId: string | null | undefined
): SessionView {
  if (isStale(view, wireId)) return view;
  const parsed = parseWireId(wireId);
  const next: SessionView = {
    ...view,
    lastEventId: parsed ? wireId! : view.lastEventId,
    lastTurnIndex: parsed ? parsed[0] : view.lastTurnIndex,
  };
  const sortKey = agentSortKey(wireId, view);
  const key = wireId ?? `${type}-${sortKey}`;

  switch (type) {
    case "thinking":
      return { ...next, thinking: data.content ?? "", busy: true };
    case "hypothesis": {
      const h: Hypothesis = {
        hypothesis_id: data.hypothesis_id,
        description: data.description,
        confidence: data.confidence,
        eliminated: data.eliminated ?? false,
      };
      const i = next.hypotheses.findIndex((x) => x.hypothesis_id === h.hypothesis_id);
      const hypotheses =
        i >= 0
          ? next.hypotheses.map((x, j) => (j === i ? h : x))
          : [...next.hypotheses, h];
      return { ...next, hypotheses };
    }
    case "question":
      return {
        ...next,
        question: {
          content: data.content,
          evidence_type: data.evidence_type,
          required_format: data.required_format ?? null,
        },
      };
    case "guidance": {
      const g: Guidance = {
        step_index: data.step_index,
        content: data.content,
        safety_level: data.safety_level ?? "low",
      };
      const i = next.guidance.findIndex((x) => x.step_index === g.step_index);
      const guidance =
        i >= 0 ? next.guidance.map((x, j) => (j === i ? g : x)) : [...next.guidance, g];
      return { ...next, guidance: guidance.sort((a, b) => a.step_index - b.step_index) };
    }
    case "diagnosis":
      return {
        ...next,
        diagnosis: {
          hypothesis_id: data.hypothesis_id,
          confidence: data.confidence,
          explanation: data.explanation,
        },
        question: null,
      };
    case "tool_call":
      return withLog(next, `🔧 ${data.tool}`, sortKey, key);
    case "tool_result":
      return withLog(next, `✅ ${data.tool}: ${data.result_summary ?? ""}`, sortKey, key);
    case "done":
      return { ...next, doneStatus: data.status ?? null, busy: false, thinking: "" };
    default:
      return withLog(next, `${type}: ${JSON.stringify(data)}`, sortKey, key);
  }
}

export type UserLogEntry = { text: string; sortKey: number; key: string };

// Build the entry from the current view, persist it, then apply — same sortKey
// in storage and on screen.
export function userEntry(view: SessionView, text: string, at: number = Date.now()): UserLogEntry {
  return { text, sortKey: (view.lastTurnIndex + 0.5) * 1000, key: `user-${at}` };
}

export function applyUserEntries(view: SessionView, entries: UserLogEntry[]): SessionView {
  return entries.reduce((v, e) => withLog(v, `👤 ${e.text}`, e.sortKey, e.key), view);
}

export function withBusy(view: SessionView, busy: boolean): SessionView {
  return { ...view, busy };
}
