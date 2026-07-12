// Feature 1.4 — dirty web prototype. Vanilla JS against the Feature 1.3 API.
// ponytail: same host serves page (:8080) and API (:8000) — no config needed
const API = `http://${location.hostname}:8000`;

const $ = (id) => document.getElementById(id);
let sessionId = null;

$("start").onclick = startSession;
$("send").onclick = sendTurn;
$("text").onkeydown = (e) => { if (e.key === "Enter") sendTurn(); };
$("photo").onchange = () => {
  const f = $("photo").files[0];
  $("cam-label").firstChild.textContent = f ? "📷✓" : "📷";
};

async function startSession() {
  $("start").disabled = true;
  try {
    const res = await fetch(`${API}/api/v1/sessions`, { method: "POST" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    sessionId = (await res.json()).session_id;
  } catch (err) {
    setStatus(`Fehler beim Start: ${err.message} — API erreichbar?`);
    $("start").disabled = false;
    return;
  }
  $("start").hidden = true;
  $("app").hidden = false;
  $("composer").hidden = false;
  setStatus("Session läuft. Foto machen oder Symptom beschreiben.");
  openStream();
}

function openStream() {
  // one stream per session; EventSource reconnects + re-sends Last-Event-ID natively
  const es = new EventSource(`${API}/api/v1/sessions/${sessionId}/stream`);
  const types = ["thinking", "hypothesis", "question", "tool_call", "tool_result",
                 "diagnosis", "guidance", "done"];
  for (const t of types) {
    es.addEventListener(t, (e) => render(t, JSON.parse(e.data)));
  }
  es.onerror = () => setStatus("Verbindung unterbrochen — verbinde neu …");
}

function render(type, ev) {
  switch (type) {
    case "thinking":
      setStatus(`🤔 ${ev.content}`);
      break;
    case "hypothesis":
      upsertHypothesis(ev);
      break;
    case "question": {
      const hint = ev.required_format ? `<div class="hint">Format: ${esc(ev.required_format)}</div>` : "";
      $("question-card").innerHTML = esc(ev.content) + hint;
      $("cam-label").classList.toggle("cta", ev.evidence_type === "photo");
      if (ev.evidence_type !== "photo") $("text").focus();
      break;
    }
    case "tool_call":
      log(`🔧 ${ev.tool} ${JSON.stringify(ev.args)}`);
      break;
    case "tool_result":
      log(`✅ ${ev.tool}: ${ev.result_summary}`);
      break;
    case "done":
      setStatus(ev.status === "awaiting_user_input" ? "Warte auf Ihre Antwort." : ev.status);
      setBusy(false);
      break;
    default:
      // diagnosis/guidance land with Feature 2.5 — visible, not styled
      log(`${type}: ${JSON.stringify(ev)}`);
  }
}

function upsertHypothesis(ev) {
  let el = document.getElementById(`hypo-${ev.hypothesis_id}`);
  if (!el) {
    el = document.createElement("div");
    el.id = `hypo-${ev.hypothesis_id}`;
    el.className = "hypo";
    $("hypotheses").appendChild(el);
  }
  el.classList.toggle("eliminated", !!ev.eliminated);
  const pct = Math.round(ev.confidence * 100);
  el.innerHTML = `${esc(ev.description)} <small>(${pct}%)</small>
    <div class="bar"><div style="width:${pct}%"></div></div>`;
}

async function sendTurn() {
  const text = $("text").value.trim();
  const file = $("photo").files[0];
  if (!text && !file) return;
  setBusy(true);
  setStatus("Sende …");
  try {
    const media_keys = file ? [await uploadPhoto(file)] : [];
    const res = await fetch(`${API}/api/v1/sessions/${sessionId}/turns`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idempotency_key: crypto.randomUUID(), text, media_keys }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    log(`👤 ${text}${file ? " 📷" : ""}`);
    $("text").value = "";
    $("photo").value = "";
    $("cam-label").firstChild.textContent = "📷";
    $("cam-label").classList.remove("cta");
  } catch (err) {
    setStatus(`Senden fehlgeschlagen: ${err.message} — bitte erneut versuchen.`);
    setBusy(false);
  }
}

async function uploadPhoto(file) {
  const type = file.type || "image/jpeg";
  const res = await fetch(`${API}/api/v1/media/upload-url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: file.name || "photo.jpg", content_type: type }),
  });
  if (!res.ok) throw new Error(`Upload-URL HTTP ${res.status}`);
  const { upload_url, media_key } = await res.json();
  // Content-Type is part of the presigned signature — must match (Feature 1.2)
  const put = await fetch(upload_url, { method: "PUT", headers: { "Content-Type": type }, body: file });
  if (!put.ok) throw new Error(`S3 PUT HTTP ${put.status}`);
  return media_key;
}

function setBusy(busy) {
  $("send").disabled = busy;
  $("text").disabled = busy;
}

function setStatus(msg) {
  $("status").textContent = msg;
}

function log(msg) {
  const div = document.createElement("div");
  div.textContent = msg;
  $("log").appendChild(div);
}

function esc(s) {
  const div = document.createElement("div");
  div.textContent = s ?? "";
  return div.innerHTML;
}
