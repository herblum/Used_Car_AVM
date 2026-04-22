import { useState, useEffect } from "react";
import {
  View,
  Text,
  TextInput,
  ScrollView,
  Pressable,
  StyleSheet,
  ActivityIndicator,
  Alert,
} from "react-native";
import { useRouter } from "expo-router";
import { predictPrice, getTrimOptions, CarFeatures } from "../lib/api";

const FUEL_OPTIONS = ["Nafta", "Diésel", "GNC", "Híbrido", "Eléctrico"];
const TRANSMISSION_OPTIONS = ["Manual", "Automática", "CVT"];
const BODY_OPTIONS = ["Sedán", "SUV", "Hatchback", "Pick-Up", "Coupé", "Familiar", "Monovolumen"];
const CURRENCY_OPTIONS = ["USD", "ARS"];

function Picker({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        {options.map((opt) => (
          <Pressable
            key={opt}
            style={[styles.chip, value === opt && styles.chipActive]}
            onPress={() => onChange(value === opt ? "" : opt)}
          >
            <Text style={[styles.chipText, value === opt && styles.chipTextActive]}>
              {opt}
            </Text>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

export default function FormScreen() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  const [marca, setMarca] = useState("");
  const [modelo, setModelo] = useState("");
  const [anio, setAnio] = useState("");
  const [kilometros, setKilometros] = useState("");
  const [cilindrada, setCilindrada] = useState("");
  const [combustible, setCombustible] = useState("");
  const [transmision, setTransmision] = useState("");
  const [tipoCarroceria, setTipoCarroceria] = useState("");
  const [moneda, setMoneda] = useState("USD");
  const [trim, setTrim] = useState("");
  const [trimOptions, setTrimOptions] = useState<string[]>([]);

  useEffect(() => {
    if (!marca) {
      setTrimOptions([]);
      setTrim("");
      return;
    }
    const timer = setTimeout(() => {
      getTrimOptions(marca).then(setTrimOptions);
    }, 400);
    return () => clearTimeout(timer);
  }, [marca]);

  async function handleSubmit() {
    if (!marca || !anio) {
      Alert.alert("Campos requeridos", "Marca y año son obligatorios.");
      return;
    }

    const features: CarFeatures = {
      marca,
      modelo: modelo || undefined,
      anio: parseInt(anio, 10),
      kilometros: kilometros ? parseFloat(kilometros) : undefined,
      cilindrada_cc: cilindrada ? parseInt(cilindrada, 10) : undefined,
      combustible: combustible || undefined,
      transmision: transmision || undefined,
      tipo_carroceria: tipoCarroceria || undefined,
      moneda,
      condicion: "used",
      trim_level: trim || undefined,
    };

    setLoading(true);
    try {
      const result = await predictPrice(features);
      router.push({
        pathname: "/results",
        params: {
          low: result.price_low.toString(),
          mid: result.price_mid.toString(),
          high: result.price_high.toString(),
          currency: result.currency,
          marca,
          modelo,
          anio,
        },
      });
    } catch (e: any) {
      Alert.alert("Error", e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.field}>
        <Text style={styles.label}>Marca *</Text>
        <TextInput style={styles.input} value={marca} onChangeText={setMarca} placeholder="Ej: Audi" />
      </View>

      <View style={styles.field}>
        <Text style={styles.label}>Modelo</Text>
        <TextInput style={styles.input} value={modelo} onChangeText={setModelo} placeholder="Ej: Q7" />
      </View>

      <View style={styles.field}>
        <Text style={styles.label}>Año *</Text>
        <TextInput style={styles.input} value={anio} onChangeText={setAnio} placeholder="Ej: 2017" keyboardType="numeric" />
      </View>

      <View style={styles.field}>
        <Text style={styles.label}>Kilómetros</Text>
        <TextInput style={styles.input} value={kilometros} onChangeText={setKilometros} placeholder="Ej: 62000" keyboardType="numeric" />
      </View>

      <View style={styles.field}>
        <Text style={styles.label}>Cilindrada (cc)</Text>
        <TextInput style={styles.input} value={cilindrada} onChangeText={setCilindrada} placeholder="Ej: 3000" keyboardType="numeric" />
      </View>

      <Picker label="Combustible" options={FUEL_OPTIONS} value={combustible} onChange={setCombustible} />
      <Picker label="Transmisión" options={TRANSMISSION_OPTIONS} value={transmision} onChange={setTransmision} />
      {trimOptions.length > 0 && (
        <Picker label="Versión / Trim" options={trimOptions} value={trim} onChange={setTrim} />
      )}
      <Picker label="Carrocería" options={BODY_OPTIONS} value={tipoCarroceria} onChange={setTipoCarroceria} />
      <Picker label="Moneda" options={CURRENCY_OPTIONS} value={moneda} onChange={setMoneda} />

      <Pressable style={styles.button} onPress={handleSubmit} disabled={loading}>
        {loading ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.buttonText}>Tasar</Text>
        )}
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f5f5f5" },
  content: { padding: 20, paddingBottom: 40 },
  field: { marginBottom: 16 },
  label: { fontSize: 14, fontWeight: "600", color: "#333", marginBottom: 6 },
  input: {
    backgroundColor: "#fff",
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
    borderWidth: 1,
    borderColor: "#ddd",
  },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: "#e0e0e0",
    marginRight: 8,
  },
  chipActive: { backgroundColor: "#1a1a2e" },
  chipText: { fontSize: 14, color: "#333" },
  chipTextActive: { color: "#fff" },
  button: {
    backgroundColor: "#1a1a2e",
    borderRadius: 10,
    padding: 16,
    alignItems: "center",
    marginTop: 24,
  },
  buttonText: { color: "#fff", fontSize: 18, fontWeight: "bold" },
});
