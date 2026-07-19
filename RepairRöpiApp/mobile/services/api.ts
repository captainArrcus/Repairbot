// Feature 2.6 — API client against the Feature 1.3/2.5 backend contract.
import Constants from "expo-constants";
import EventSource from "react-native-sse";

const extra = (Constants.expoConfig?.extra ?? {}) as {
  apiUrl?: string | null;
  tenantId?: string | null;
};

// Dev (Expo Go): Metro host == laptop LAN IP → API on :8000, same pattern as the
// 1.4 web prototype — always wins so the dev loop stays zero-config. APKs have
// no Metro host and fall back to the baked extra.apiUrl.
export function apiBase(): string {
  const host = Constants.expoConfig?.hostUri?.split(":")[0];
  if (host) return `http://${host}:8000`;
  if (extra.apiUrl) return extra.apiUrl.replace(/\/+$/, "");
  throw new Error("Keine API-URL konfiguriert (app.json → extra.apiUrl)");
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
  }
}

function baseHeaders(): Record<string, string> {
  return extra.tenantId ? { "X-Tenant-Id": extra.tenantId } : {};
}

async function jsonFetch(path: string, init?: RequestInit): Promise<any> {
  const res = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...baseHeaders(), ...init?.headers },
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

export async function createSession(): Promise<string> {
  const data = await jsonFetch("/api/v1/sessions", { method: "POST", body: JSON.stringify({}) });
  return data.session_id;
}

export async function sendTurn(
  sessionId: string,
  body: { idempotency_key: string; text: string; media_keys: string[] }
): Promise<string> {
  const data = await jsonFetch(`/api/v1/sessions/${sessionId}/turns`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  return data.turn_id;
}

export async function recordOutcome(
  sessionId: string,
  outcome: "resolved" | "escalated" | "failed",
  verificationMediaRef?: string | null
): Promise<void> {
  await jsonFetch(`/api/v1/sessions/${sessionId}/outcome`, {
    method: "POST",
    body: JSON.stringify({ outcome, verification_media_ref: verificationMediaRef ?? null }),
  });
}

// Presign + direct PUT (Feature 1.2). Content-Type is part of the signature.
export async function uploadMedia(
  localUri: string,
  contentType: string,
  filename: string
): Promise<string> {
  const { upload_url, media_key } = await jsonFetch("/api/v1/media/upload-url", {
    method: "POST",
    body: JSON.stringify({ filename, content_type: contentType }),
  });
  const blob = await (await fetch(localUri)).blob();
  const put = await fetch(upload_url, {
    method: "PUT",
    headers: { "Content-Type": contentType },
    body: blob,
  });
  if (!put.ok) throw new ApiError(put.status, `Upload fehlgeschlagen (HTTP ${put.status})`);
  return media_key;
}

export const EVENT_TYPES = [
  "thinking",
  "hypothesis",
  "question",
  "tool_call",
  "tool_result",
  "diagnosis",
  "guidance",
  "done",
] as const;

export type StreamHandle = { close: () => void };

// Fresh connect replays the whole session (server cursor starts at -1,-1);
// reconnects pass Last-Event-ID. The reducer's monotonic filter dedupes either way.
export function openStream(
  sessionId: string,
  lastEventId: string | null,
  onEvent: (type: string, data: any, id: string | null) => void,
  onError: (status?: number) => void
): StreamHandle {
  const es = new EventSource(`${apiBase()}/api/v1/sessions/${sessionId}/stream`, {
    headers: {
      ...baseHeaders(),
      ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
    },
    pollingInterval: 0, // reconnect handled by the screen (fresh Last-Event-ID)
  });
  for (const t of EVENT_TYPES) {
    es.addEventListener(t as any, (e: any) => {
      if (e?.data) onEvent(t, JSON.parse(e.data), e.lastEventId ?? null);
    });
  }
  es.addEventListener("error", (e: any) => onError(e?.xhrStatus));
  return {
    close: () => {
      es.removeAllEventListeners();
      es.close();
    },
  };
}
