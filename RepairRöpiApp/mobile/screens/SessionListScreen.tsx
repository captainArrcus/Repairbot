import { useEffect, useState } from "react";
import {
  Alert,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { colors } from "../components/theme";
import { createSession } from "../services/api";
import { listSessions, removeSession, upsertSession, type SessionMeta } from "../services/store";

const STATUS_LABEL: Record<SessionMeta["status"], string> = {
  active: "aktiv",
  resolved: "behoben",
  escalated: "eskaliert",
  failed: "nicht behoben",
};

export default function SessionListScreen({ onOpen }: { onOpen: (id: string) => void }) {
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSessions().then(setSessions);
  }, []);

  async function newSession() {
    setCreating(true);
    setError(null);
    try {
      const id = await createSession();
      await upsertSession({ id });
      onOpen(id);
    } catch (err: any) {
      setError(`Session-Start fehlgeschlagen: ${err.message} — Backend erreichbar?`);
    } finally {
      setCreating(false);
    }
  }

  function confirmRemove(s: SessionMeta) {
    Alert.alert("Session entfernen?", "Nur von diesem Gerät. Serverdaten bleiben erhalten.", [
      { text: "Abbrechen", style: "cancel" },
      {
        text: "Entfernen",
        style: "destructive",
        onPress: async () => {
          await removeSession(s.id);
          setSessions(await listSessions());
        },
      },
    ]);
  }

  return (
    <View style={styles.root}>
      <Text style={styles.title}>
        RepairRöpi <Text style={styles.subtitle}>Diagnose-Partner</Text>
      </Text>
      {error && <Text style={styles.error}>{error}</Text>}
      <Pressable style={styles.newBtn} onPress={newSession} disabled={creating}>
        <Text style={styles.newBtnText}>{creating ? "Starte …" : "+ Neue Diagnose"}</Text>
      </Pressable>
      <FlatList
        data={sessions}
        keyExtractor={(s) => s.id}
        ListEmptyComponent={<Text style={styles.empty}>Noch keine Sessions auf diesem Gerät.</Text>}
        renderItem={({ item }) => (
          <Pressable
            style={styles.row}
            onPress={() => onOpen(item.id)}
            onLongPress={() => confirmRemove(item)}
          >
            <View style={styles.rowText}>
              <Text style={styles.label} numberOfLines={1}>
                {item.label}
              </Text>
              <Text style={styles.meta}>
                {new Date(item.createdAt).toLocaleString("de-DE", {
                  day: "2-digit",
                  month: "2-digit",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </Text>
            </View>
            <Text style={[styles.status, item.status !== "active" && styles.statusDone]}>
              {STATUS_LABEL[item.status]}
            </Text>
          </Pressable>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, padding: 16 },
  title: { color: colors.text, fontSize: 22, fontWeight: "700", marginBottom: 16 },
  subtitle: { color: colors.dim, fontSize: 14, fontWeight: "400" },
  error: { color: colors.warn, marginBottom: 10 },
  newBtn: {
    backgroundColor: colors.ok,
    borderRadius: 8,
    padding: 14,
    alignItems: "center",
    marginBottom: 16,
  },
  newBtnText: { color: "#fff", fontSize: 17, fontWeight: "600" },
  empty: { color: colors.dim, textAlign: "center", marginTop: 40 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.card,
    borderRadius: 8,
    padding: 12,
    marginBottom: 8,
  },
  rowText: { flex: 1, marginRight: 8 },
  label: { color: colors.text, fontSize: 15 },
  meta: { color: colors.dim, fontSize: 12, marginTop: 2 },
  status: { color: colors.accent, fontSize: 12 },
  statusDone: { color: colors.dim },
});
