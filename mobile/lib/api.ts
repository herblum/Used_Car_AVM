const API_BASE = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

export interface CarFeatures {
  marca?: string;
  modelo?: string;
  anio?: number;
  kilometros?: number;
  cilindrada_cc?: number;
  combustible?: string;
  transmision?: string;
  traccion?: string;
  tipo_carroceria?: string;
  puertas?: number;
  color?: string;
  provincia?: string;
  moneda?: string;
  condicion?: string;
  es_concesionario?: number;
}

export interface PriceRange {
  price_low: number;
  price_mid: number;
  price_high: number;
  currency: string;
}

export async function predictPrice(features: CarFeatures): Promise<PriceRange> {
  const res = await fetch(`${API_BASE}/predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(features),
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Prediction failed: ${detail}`);
  }

  return res.json();
}
