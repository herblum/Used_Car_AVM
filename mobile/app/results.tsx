import { View, Text, Pressable, StyleSheet } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";

function formatPrice(value: string, currency: string): string {
  const num = parseFloat(value);
  if (currency === "USD") {
    return `US$ ${num.toLocaleString("es-AR", { maximumFractionDigits: 0 })}`;
  }
  return `$ ${num.toLocaleString("es-AR", { maximumFractionDigits: 0 })}`;
}

export default function ResultsScreen() {
  const router = useRouter();
  const { low, mid, high, currency, marca, modelo, anio } = useLocalSearchParams<{
    low: string;
    mid: string;
    high: string;
    currency: string;
    marca: string;
    modelo: string;
    anio: string;
  }>();

  const title = [marca, modelo, anio].filter(Boolean).join(" ");

  return (
    <View style={styles.container}>
      <Text style={styles.carTitle}>{title}</Text>

      <View style={styles.card}>
        <View style={styles.row}>
          <Text style={styles.labelLow}>Mínimo</Text>
          <Text style={styles.priceLow}>{formatPrice(low, currency)}</Text>
        </View>

        <View style={styles.divider} />

        <View style={styles.row}>
          <Text style={styles.labelMid}>Precio estimado</Text>
          <Text style={styles.priceMid}>{formatPrice(mid, currency)}</Text>
        </View>

        <View style={styles.divider} />

        <View style={styles.row}>
          <Text style={styles.labelHigh}>Máximo</Text>
          <Text style={styles.priceHigh}>{formatPrice(high, currency)}</Text>
        </View>
      </View>

      <Text style={styles.disclaimer}>
        Basado en publicaciones recientes de MercadoLibre. Los valores son estimativos.
      </Text>

      <Pressable style={styles.button} onPress={() => router.back()}>
        <Text style={styles.buttonText}>Nueva consulta</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5", padding: 20, justifyContent: "center" },
  carTitle: { fontSize: 22, fontWeight: "bold", color: "#1a1a2e", textAlign: "center", marginBottom: 24 },
  card: {
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 20,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 3,
  },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 12 },
  divider: { height: 1, backgroundColor: "#eee" },
  labelLow: { fontSize: 14, color: "#888" },
  labelMid: { fontSize: 16, fontWeight: "600", color: "#1a1a2e" },
  labelHigh: { fontSize: 14, color: "#888" },
  priceLow: { fontSize: 18, color: "#888" },
  priceMid: { fontSize: 28, fontWeight: "bold", color: "#1a1a2e" },
  priceHigh: { fontSize: 18, color: "#888" },
  disclaimer: { fontSize: 12, color: "#999", textAlign: "center", marginTop: 20 },
  button: {
    backgroundColor: "#1a1a2e",
    borderRadius: 10,
    padding: 16,
    alignItems: "center",
    marginTop: 32,
  },
  buttonText: { color: "#fff", fontSize: 18, fontWeight: "bold" },
});
