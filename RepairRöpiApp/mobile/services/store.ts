// Feature 2.6 — local persistence: session list, per-session user log,
// pending-turn queue (offline resilience). Server stays source of truth for
// agent state (SSE replay); this is the phone-only remainder.
import AsyncStorage from "@react-native-async-storage/async-storage";

import type { UserLogEntry } from "./events";

export type SessionMeta = {
  id: string;
  createdAt: string;
  label: string;
  status: "active" | "resolved" | "escalated" | "failed";
};

export type PendingMedia = {
  localUri: string;
  contentType: string;
  filename: string;
  mediaKey: string | null; // set once uploaded — survives retries (Roadmap: cache uploaded media_keys)
};

export type PendingTurn = {
  idempotencyKey: string;
  text: string;
  media: PendingMedia[];
};

const SESSIONS = "rr.sessions";
const userLogKey = (id: string) => `rr.userlog.${id}`;
const pendingKey = (id: string) => `rr.pending.${id}`;

async function readJson<T>(key: string, fallback: T): Promise<T> {
  const raw = await AsyncStorage.getItem(key);
  return raw ? (JSON.parse(raw) as T) : fallback;
}

export async function listSessions(): Promise<SessionMeta[]> {
  return readJson<SessionMeta[]>(SESSIONS, []);
}

export async function upsertSession(meta: Partial<SessionMeta> & { id: string }): Promise<void> {
  const sessions = await listSessions();
  const i = sessions.findIndex((s) => s.id === meta.id);
  if (i >= 0) sessions[i] = { ...sessions[i], ...meta };
  else
    sessions.unshift({
      createdAt: new Date().toISOString(),
      label: "Neue Session",
      status: "active",
      ...meta,
    });
  await AsyncStorage.setItem(SESSIONS, JSON.stringify(sessions));
}

export async function removeSession(id: string): Promise<void> {
  const sessions = (await listSessions()).filter((s) => s.id !== id);
  await AsyncStorage.setItem(SESSIONS, JSON.stringify(sessions));
  await AsyncStorage.multiRemove([userLogKey(id), pendingKey(id)]);
}

export async function loadUserLog(id: string): Promise<UserLogEntry[]> {
  return readJson<UserLogEntry[]>(userLogKey(id), []);
}

export async function appendUserLog(id: string, entry: UserLogEntry): Promise<void> {
  const log = await loadUserLog(id);
  log.push(entry);
  await AsyncStorage.setItem(userLogKey(id), JSON.stringify(log));
}

export async function loadPending(id: string): Promise<PendingTurn | null> {
  return readJson<PendingTurn | null>(pendingKey(id), null);
}

export async function savePending(id: string, pending: PendingTurn): Promise<void> {
  await AsyncStorage.setItem(pendingKey(id), JSON.stringify(pending));
}

export async function clearPending(id: string): Promise<void> {
  await AsyncStorage.removeItem(pendingKey(id));
}
