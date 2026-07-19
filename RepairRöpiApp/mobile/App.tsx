import { StatusBar } from "expo-status-bar";
import { useState } from "react";
import { SafeAreaView, StyleSheet } from "react-native";

import { colors } from "./components/theme";
import SessionListScreen from "./screens/SessionListScreen";
import SessionScreen from "./screens/SessionScreen";

// ponytail: two screens, conditional render — no navigation library
export default function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  return (
    <SafeAreaView style={styles.root}>
      <StatusBar style="light" />
      {sessionId ? (
        <SessionScreen sessionId={sessionId} onBack={() => setSessionId(null)} />
      ) : (
        <SessionListScreen onOpen={setSessionId} />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
});
