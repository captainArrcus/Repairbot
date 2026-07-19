import * as Crypto from "expo-crypto";
import * as ImagePicker from "expo-image-picker";
import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from "expo-audio";
import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import HypothesisList from "../components/HypothesisList";
import { colors } from "../components/theme";
import { ApiError, openStream, recordOutcome, sendTurn, uploadMedia } from "../services/api";
import {
  applyEvent,
  applyUserEntries,
  emptyView,
  userEntry,
  withBusy,
  type SessionView,
} from "../services/events";
import {
  appendUserLog,
  clearPending,
  loadPending,
  loadUserLog,
  removeSession,
  savePending,
  upsertSession,
  type PendingTurn,
} from "../services/store";

type Props = { sessionId: string; onBack: () => void };

type Attachment = { uri: string; type: string; name: string };

export default function SessionScreen({ sessionId, onBack }: Props) {
  const [view, setView] = useState<SessionView>(emptyView());
  const viewRef = useRef(view);
  const [connected, setConnected] = useState(false);
  const [text, setText] = useState("");
  const [photo, setPhoto] = useState<Attachment | null>(null);
  const [audio, setAudio] = useState<Attachment | null>(null);
  const [pending, setPending] = useState<PendingTurn | null>(null);
  const pendingRef = useRef(pending);
  const sendingRef = useRef(false);
  const [sending, setSending] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [closed, setClosed] = useState<string | null>(null);

  const recorder = useAudioRecorder({ ...RecordingPresets.HIGH_QUALITY, isMeteringEnabled: true });
  const recState = useAudioRecorderState(recorder, 200);

  useEffect(() => {
    viewRef.current = view;
  }, [view]);
  useEffect(() => {
    pendingRef.current = pending;
  }, [pending]);

  // Restore phone-local state (user log, unsent turn); agent state comes from SSE replay.
  useEffect(() => {
    loadUserLog(sessionId).then((entries) =>
      setView((v) => applyUserEntries(v, entries))
    );
    loadPending(sessionId).then(setPending);
  }, [sessionId]);

  useEffect(() => {
    let disposed = false;
    let handle: { close: () => void } | null = null;
    let timer: ReturnType<typeof setTimeout>;
    const connect = () => {
      if (disposed) return;
      handle = openStream(
        sessionId,
        viewRef.current.lastEventId,
        (type, data, id) => {
          setConnected(true);
          setView((v) => applyEvent(v, type, data, id));
        },
        (status) => {
          setConnected(false);
          handle?.close();
          if (status === 404) {
            Alert.alert("Session nicht gefunden", "Sie wird von diesem Gerät entfernt.", [
              { text: "OK", onPress: () => removeSession(sessionId).then(onBack) },
            ]);
            return;
          }
          timer = setTimeout(connect, 3000);
        }
      );
    };
    connect();
    return () => {
      disposed = true;
      clearTimeout(timer);
      handle?.close();
    };
  }, [sessionId]);

  // Offline resilience: retry the queued turn until the network is back.
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(() => attempt(pendingRef.current), 8000);
    return () => clearInterval(t);
  }, [pending?.idempotencyKey]);

  async function attempt(p: PendingTurn | null) {
    if (!p || sendingRef.current) return;
    sendingRef.current = true;
    setSending(true);
    try {
      const keys: string[] = [];
      for (const m of p.media) {
        if (!m.mediaKey) {
          m.mediaKey = await uploadMedia(m.localUri, m.contentType, m.filename);
          await savePending(sessionId, p); // uploaded key survives the next retry
        }
        keys.push(m.mediaKey);
      }
      await sendTurn(sessionId, {
        idempotency_key: p.idempotencyKey,
        text: p.text,
        media_keys: keys,
      });
      const label = [
        p.text,
        p.media.some((m) => m.contentType.startsWith("image/")) ? "📷" : "",
        p.media.some((m) => m.contentType.startsWith("audio/")) ? "🎤" : "",
      ]
        .filter(Boolean)
        .join(" ");
      const entry = userEntry(viewRef.current, label);
      await appendUserLog(sessionId, entry);
      if (viewRef.current.lastTurnIndex === 0)
        await upsertSession({ id: sessionId, label: label.slice(0, 60) });
      setView((v) => withBusy(applyUserEntries(v, [entry]), true));
      await clearPending(sessionId);
      setPending(null);
      setToast(null);
    } catch (err: any) {
      if (err instanceof ApiError && (err.status === 422 || err.status === 404)) {
        await clearPending(sessionId);
        setPending(null);
        setToast(`Antwort verworfen: ${err.message}`);
      } else if (err instanceof ApiError && err.status === 409) {
        setToast("Agent arbeitet noch — wird gleich erneut gesendet.");
      } else {
        setToast("Keine Verbindung — Antwort wartet und wird automatisch erneut gesendet.");
      }
    } finally {
      sendingRef.current = false;
      setSending(false);
    }
  }

  async function submitTurn(turnText: string, media: Attachment[]) {
    const p: PendingTurn = {
      idempotencyKey: Crypto.randomUUID(),
      text: turnText.trim(),
      media: media.map((m) => ({
        localUri: m.uri,
        contentType: m.type,
        filename: m.name,
        mediaKey: null,
      })),
    };
    if (!p.text && p.media.length === 0) return;
    await savePending(sessionId, p);
    setPending(p);
    attempt(p);
  }

  function send() {
    const media = [photo, audio].filter((a): a is Attachment => a !== null);
    submitTurn(text, media);
    setText("");
    setPhoto(null);
    setAudio(null);
  }

  async function takePhoto() {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) {
      setToast("Kamerazugriff verweigert.");
      return;
    }
    const res = await ImagePicker.launchCameraAsync({ quality: 0.7 });
    if (!res.canceled && res.assets[0]) {
      const a = res.assets[0];
      setPhoto({ uri: a.uri, type: a.mimeType ?? "image/jpeg", name: a.fileName ?? "foto.jpg" });
    }
  }

  async function toggleRecording() {
    if (recState.isRecording) {
      await recorder.stop();
      if (recorder.uri)
        setAudio({ uri: recorder.uri, type: "audio/m4a", name: "sprachnotiz.m4a" });
      return;
    }
    const perm = await AudioModule.requestRecordingPermissionsAsync();
    if (!perm.granted) {
      setToast("Mikrofonzugriff verweigert.");
      return;
    }
    await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
    await recorder.prepareToRecordAsync();
    recorder.record();
  }

  async function finishSession(outcome: "resolved" | "escalated" | "failed") {
    try {
      await recordOutcome(sessionId, outcome);
      await upsertSession({ id: sessionId, status: outcome });
      setClosed(outcome);
    } catch (err: any) {
      setToast(`Abschluss fehlgeschlagen: ${err.message}`);
    }
  }

  const q = view.question;
  const highSafetyOpen =
    !view.busy &&
    view.doneStatus === "awaiting_user_input" &&
    view.guidance.some((g) => g.safety_level === "high") &&
    view.guidance[view.guidance.length - 1]?.safety_level === "high";
  const meterDb = recState.metering ?? -60;
  const meterPct = Math.max(0, Math.min(1, (meterDb + 60) / 60)) * 100;

  return (
    <View style={styles.root}>
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12}>
          <Text style={styles.back}>‹ Sessions</Text>
        </Pressable>
        <View style={[styles.dot, { backgroundColor: connected ? colors.ok : colors.danger }]} />
      </View>

      <View style={styles.statusRow}>
        {(view.busy || sending) && <ActivityIndicator size="small" color={colors.accent} />}
        <Text style={styles.status} numberOfLines={2}>
          {sending
            ? "Sende …"
            : view.busy
              ? view.thinking
                ? `🤔 ${view.thinking}`
                : "Agent arbeitet …"
              : view.doneStatus === "awaiting_verification"
                ? "Warte auf Verifikation."
                : view.doneStatus === "complete"
                  ? "Diagnose abgeschlossen."
                  : "Bereit."}
        </Text>
      </View>

      <ScrollView style={styles.main} contentContainerStyle={{ paddingBottom: 16 }}>
        {view.diagnosis && (
          <View style={styles.diagnosisCard}>
            <Text style={styles.diagnosisTitle}>
              Diagnose ({Math.round(view.diagnosis.confidence * 100)} %)
            </Text>
            <Text style={styles.cardText}>{view.diagnosis.explanation}</Text>
          </View>
        )}

        {q && !closed && (
          <View style={styles.questionCard}>
            <Text style={styles.cardText}>{q.content}</Text>
            {q.required_format ? (
              <Text style={styles.hint}>Format: {q.required_format}</Text>
            ) : null}
          </View>
        )}

        {view.doneStatus === "awaiting_verification" && !closed && (
          <View style={styles.verifyCard}>
            <Text style={styles.cardText}>
              Reparatur durchführen, Verifikationsfoto senden — dann Session abschließen:
            </Text>
            <View style={styles.outcomeRow}>
              <Pressable style={[styles.outcomeBtn, { backgroundColor: colors.ok }]} onPress={() => finishSession("resolved")}>
                <Text style={styles.outcomeText}>✅ Behoben</Text>
              </Pressable>
              <Pressable style={[styles.outcomeBtn, { backgroundColor: colors.warn }]} onPress={() => finishSession("escalated")}>
                <Text style={styles.outcomeText}>📞 Eskaliert</Text>
              </Pressable>
              <Pressable style={[styles.outcomeBtn, { backgroundColor: colors.danger }]} onPress={() => finishSession("failed")}>
                <Text style={styles.outcomeText}>✗ Nicht behoben</Text>
              </Pressable>
            </View>
          </View>
        )}

        {closed && (
          <View style={styles.card}>
            <Text style={styles.cardText}>Session abgeschlossen ({closed}).</Text>
          </View>
        )}

        <HypothesisList hypotheses={view.hypotheses} />

        {view.guidance.length > 0 && (
          <View>
            <Text style={styles.heading}>Anleitung</Text>
            {view.guidance.map((g) => (
              <View
                key={g.step_index}
                style={[
                  styles.card,
                  g.safety_level === "high" && styles.guidanceHigh,
                  g.safety_level === "medium" && styles.guidanceMedium,
                ]}
              >
                <Text style={styles.cardText}>
                  {g.step_index}. {g.content}
                </Text>
                {g.safety_level === "high" && (
                  <Text style={styles.safetyTag}>⚠️ Sicherheitsrelevant</Text>
                )}
              </View>
            ))}
            {highSafetyOpen && (
              <Pressable
                style={styles.confirmBtn}
                onPress={() => submitTurn("Bestätigt: Sicherheitsschritt umgesetzt.", [])}
              >
                <Text style={styles.confirmText}>⚠️ Schritt umgesetzt — weiter</Text>
              </Pressable>
            )}
          </View>
        )}

        {view.log.length > 0 && (
          <View>
            <Text style={styles.heading}>Protokoll</Text>
            {view.log.map((l) => (
              <Text key={l.key} style={styles.logLine}>
                {l.text}
              </Text>
            ))}
          </View>
        )}
      </ScrollView>

      {toast && <Text style={styles.toast}>{toast}</Text>}

      {pending && (
        <View style={styles.pendingBar}>
          <Text style={styles.pendingText}>Antwort noch nicht gesendet.</Text>
          <Pressable onPress={() => attempt(pendingRef.current)}>
            <Text style={styles.pendingAction}>Erneut senden</Text>
          </Pressable>
          <Pressable
            onPress={() => clearPending(sessionId).then(() => setPending(null))}
          >
            <Text style={[styles.pendingAction, { color: colors.danger }]}>Verwerfen</Text>
          </Pressable>
        </View>
      )}

      {recState.isRecording && (
        <View style={styles.recordBar}>
          <Text style={styles.recordText}>
            🎤 {Math.floor((recState.durationMillis ?? 0) / 1000)}s — Umgebungslärm:
          </Text>
          <View style={styles.meterBg}>
            <View
              style={[
                styles.meter,
                { width: `${meterPct}%` },
                meterPct > 75 && { backgroundColor: colors.danger },
              ]}
            />
          </View>
        </View>
      )}

      {(photo || audio) && (
        <View style={styles.attachRow}>
          {photo && (
            <Pressable onPress={() => setPhoto(null)}>
              <Text style={styles.chip}>📷 Foto ✕</Text>
            </Pressable>
          )}
          {audio && (
            <Pressable onPress={() => setAudio(null)}>
              <Text style={styles.chip}>🎤 Sprachnotiz ✕</Text>
            </Pressable>
          )}
        </View>
      )}

      <View style={styles.composer}>
        <Pressable
          style={[styles.iconBtn, q?.evidence_type === "photo" && styles.cta]}
          onPress={takePhoto}
          disabled={!!pending}
        >
          <Text style={styles.iconText}>📷</Text>
        </Pressable>
        <Pressable
          style={[
            styles.iconBtn,
            q?.evidence_type === "audio" && styles.cta,
            recState.isRecording && { backgroundColor: colors.danger },
          ]}
          onPress={toggleRecording}
          disabled={!!pending}
        >
          <Text style={styles.iconText}>{recState.isRecording ? "■" : "🎤"}</Text>
        </Pressable>
        <TextInput
          style={styles.input}
          value={text}
          onChangeText={setText}
          placeholder={
            q?.evidence_type === "numeric" && q.required_format
              ? `Wert in ${q.required_format}`
              : "Symptom / Antwort …"
          }
          placeholderTextColor={colors.dim}
          inputMode={q?.evidence_type === "numeric" ? "decimal" : "text"}
          editable={!pending}
          onSubmitEditing={send}
        />
        <Pressable
          style={[styles.sendBtn, (!!pending || sending) && { opacity: 0.4 }]}
          onPress={send}
          disabled={!!pending || sending}
        >
          <Text style={styles.iconText}>➤</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: colors.card,
  },
  back: { color: colors.accent, fontSize: 16 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  statusRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 6,
    minHeight: 32,
  },
  status: { color: "#88ffdd", fontSize: 13, flex: 1 },
  main: { flex: 1, paddingHorizontal: 16 },
  heading: {
    color: colors.dim,
    fontSize: 12,
    textTransform: "uppercase",
    marginTop: 14,
    marginBottom: 4,
  },
  card: { backgroundColor: colors.card, borderRadius: 6, padding: 10, marginBottom: 5 },
  cardText: { color: colors.text, fontSize: 15, lineHeight: 21 },
  questionCard: {
    backgroundColor: colors.cardAlt,
    borderLeftWidth: 4,
    borderLeftColor: colors.accent,
    borderRadius: 6,
    padding: 12,
    marginTop: 8,
  },
  hint: { color: colors.dim, fontSize: 13, marginTop: 6 },
  diagnosisCard: {
    backgroundColor: "#1d3328",
    borderLeftWidth: 4,
    borderLeftColor: colors.ok,
    borderRadius: 6,
    padding: 12,
    marginTop: 8,
  },
  diagnosisTitle: { color: colors.ok, fontWeight: "700", marginBottom: 4, fontSize: 15 },
  verifyCard: {
    backgroundColor: colors.cardAlt,
    borderRadius: 6,
    padding: 12,
    marginTop: 8,
  },
  outcomeRow: { flexDirection: "row", gap: 6, marginTop: 10 },
  outcomeBtn: { flex: 1, borderRadius: 6, padding: 8, alignItems: "center" },
  outcomeText: { color: "#fff", fontSize: 12, fontWeight: "600" },
  guidanceHigh: { borderLeftWidth: 4, borderLeftColor: colors.danger },
  guidanceMedium: { borderLeftWidth: 4, borderLeftColor: colors.warn },
  safetyTag: { color: colors.danger, fontSize: 12, marginTop: 4 },
  confirmBtn: {
    backgroundColor: colors.danger,
    borderRadius: 6,
    padding: 12,
    alignItems: "center",
    marginTop: 4,
  },
  confirmText: { color: "#fff", fontWeight: "700" },
  logLine: { color: colors.dim, fontSize: 12, fontFamily: "monospace", marginTop: 2 },
  toast: { color: colors.warn, paddingHorizontal: 16, paddingBottom: 4, fontSize: 13 },
  pendingBar: {
    flexDirection: "row",
    gap: 12,
    alignItems: "center",
    backgroundColor: colors.cardAlt,
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  pendingText: { color: colors.text, flex: 1, fontSize: 13 },
  pendingAction: { color: colors.accent, fontSize: 13, fontWeight: "600" },
  recordBar: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: colors.card,
  },
  recordText: { color: colors.text, fontSize: 13 },
  meterBg: { flex: 1, height: 6, backgroundColor: "#334455", borderRadius: 3 },
  meter: { height: 6, backgroundColor: colors.ok, borderRadius: 3 },
  attachRow: {
    flexDirection: "row",
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 6,
  },
  chip: {
    color: colors.text,
    backgroundColor: colors.cardAlt,
    borderRadius: 12,
    paddingHorizontal: 10,
    paddingVertical: 4,
    fontSize: 13,
  },
  composer: {
    flexDirection: "row",
    gap: 6,
    padding: 10,
    backgroundColor: colors.card,
    alignItems: "center",
  },
  iconBtn: {
    backgroundColor: "#334455",
    borderRadius: 6,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  cta: { backgroundColor: colors.warn },
  iconText: { fontSize: 16, color: "#fff" },
  input: {
    flex: 1,
    backgroundColor: "#2a323b",
    color: colors.text,
    borderRadius: 6,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
  },
  sendBtn: {
    backgroundColor: colors.ok,
    borderRadius: 6,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
});
