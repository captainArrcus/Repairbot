import { StyleSheet, Text, View } from "react-native";

import type { Hypothesis } from "../services/events";
import { colors } from "./theme";

export default function HypothesisList({ hypotheses }: { hypotheses: Hypothesis[] }) {
  if (hypotheses.length === 0) return null;
  const sorted = [...hypotheses].sort(
    (a, b) => Number(a.eliminated) - Number(b.eliminated) || b.confidence - a.confidence
  );
  return (
    <View>
      <Text style={styles.heading}>Hypothesen</Text>
      {sorted.map((h) => {
        const pct = Math.round(h.confidence * 100);
        return (
          <View key={h.hypothesis_id} style={[styles.card, h.eliminated && styles.eliminated]}>
            <Text style={[styles.desc, h.eliminated && styles.strike]}>
              {h.description} <Text style={styles.pct}>({pct}%)</Text>
            </Text>
            <View style={styles.barBg}>
              <View style={[styles.bar, { width: `${pct}%` }]} />
            </View>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  heading: {
    color: colors.dim,
    fontSize: 12,
    textTransform: "uppercase",
    marginTop: 14,
    marginBottom: 4,
  },
  card: {
    backgroundColor: colors.card,
    borderRadius: 6,
    padding: 10,
    marginBottom: 5,
  },
  eliminated: { opacity: 0.45 },
  desc: { color: colors.text, fontSize: 15 },
  strike: { textDecorationLine: "line-through" },
  pct: { color: colors.dim, fontSize: 13 },
  barBg: { height: 4, backgroundColor: "#334455", borderRadius: 2, marginTop: 6 },
  bar: { height: 4, backgroundColor: colors.accent, borderRadius: 2 },
});
