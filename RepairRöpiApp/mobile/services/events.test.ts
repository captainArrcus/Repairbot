// Run: node --test services/events.test.ts  (Node ≥23 strips types natively)
import { test } from "node:test";
import assert from "node:assert/strict";
import { applyEvent, applyUserEntries, emptyView, userEntry } from "./events.ts";

test("hypothesis upsert + elimination", () => {
  let v = emptyView();
  v = applyEvent(v, "hypothesis", { hypothesis_id: "h1", description: "Lager", confidence: 0.55 }, "1.0");
  v = applyEvent(v, "hypothesis", { hypothesis_id: "h2", description: "Kupplung", confidence: 0.3 }, "1.1");
  v = applyEvent(v, "hypothesis", { hypothesis_id: "h2", description: "Kupplung", confidence: 0.05, eliminated: true }, "3.0");
  assert.equal(v.hypotheses.length, 2);
  assert.equal(v.hypotheses[1].eliminated, true);
  assert.equal(v.hypotheses[0].confidence, 0.55);
});

test("monotonic id filter drops replayed events", () => {
  let v = emptyView();
  v = applyEvent(v, "thinking", { content: "a" }, "1.0");
  v = applyEvent(v, "done", { status: "awaiting_user_input" }, "1.1");
  const before = v;
  v = applyEvent(v, "thinking", { content: "a" }, "1.0"); // replay
  assert.equal(v, before);
  v = applyEvent(v, "thinking", { content: "b" }, "1.2"); // fresh
  assert.equal(v.thinking, "b");
  assert.equal(v.busy, true);
});

test("done clears busy + thinking, question flow", () => {
  let v = emptyView();
  v = applyEvent(v, "question", { content: "Spiel?", evidence_type: "numeric", required_format: "mm" }, "1.0");
  assert.equal(v.question?.required_format, "mm");
  v = applyEvent(v, "diagnosis", { hypothesis_id: "h1", confidence: 0.9, explanation: "x" }, "1.1");
  assert.equal(v.question, null);
  v = applyEvent(v, "done", { status: "awaiting_verification" }, "1.2");
  assert.equal(v.busy, false);
  assert.equal(v.doneStatus, "awaiting_verification");
});

test("guidance upserts by step_index, keeps order", () => {
  let v = emptyView();
  v = applyEvent(v, "guidance", { step_index: 2, content: "b", safety_level: "high" }, "1.1");
  v = applyEvent(v, "guidance", { step_index: 1, content: "a", safety_level: "low" }, "1.2");
  v = applyEvent(v, "guidance", { step_index: 2, content: "b2", safety_level: "high" }, "3.0");
  assert.deepEqual(v.guidance.map((g) => [g.step_index, g.content]), [[1, "a"], [2, "b2"]]);
});

test("user entries interleave before the agent turn that answers them", () => {
  let v = emptyView();
  const e1 = userEntry(v, "Maschine rattert", {}, 1); // lastTurnIndex 0 → sortKey 500
  v = applyUserEntries(v, [e1]);
  v = applyEvent(v, "tool_call", { tool: "error_code_lookup", args: {} }, "1.0");
  v = applyEvent(v, "done", { status: "awaiting_user_input" }, "1.1");
  const e2 = userEntry(v, "0.5mm Spiel", {}, 2); // lastTurnIndex 1 → sortKey 1500
  v = applyUserEntries(v, [e2]);
  v = applyEvent(v, "tool_result", { tool: "x", result_summary: "ok" }, "3.0");
  assert.deepEqual(
    v.log.map((l) => [l.kind, l.text]),
    [
      ["user", "Maschine rattert"],
      ["agent", "🔧 error_code_lookup"],
      ["user", "0.5mm Spiel"],
      ["agent", "✅ x: ok"],
    ]
  );
  // restore path is idempotent
  const restored = applyUserEntries(v, [e1, e2]);
  assert.equal(restored.log.length, v.log.length);
});

test("user entry carries inline media into the log (2.9)", () => {
  let v = emptyView();
  const e = userEntry(v, "", { photoUri: "file:///cache/p.jpg", audioDurationMs: 12300 }, 1);
  v = applyUserEntries(v, [e]);
  assert.equal(v.log.length, 1);
  assert.equal(v.log[0].kind, "user");
  assert.equal(v.log[0].photoUri, "file:///cache/p.jpg");
  assert.equal(v.log[0].audioDurationMs, 12300);
  // pre-2.9 stored entries (no media fields) still restore
  const old = { text: "alt", sortKey: 500, key: "user-old" };
  const v2 = applyUserEntries(v, [old]);
  assert.equal(v2.log.some((l) => l.key === "user-old" && l.kind === "user"), true);
});
