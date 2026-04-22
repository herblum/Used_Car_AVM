# ─────────────────────────────────────────────
#  parser.py — markdown → feature dict
#  Extracts the fields defined in ml_feature_mapping.jsx
# ─────────────────────────────────────────────
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Optional


# ── Helper ────────────────────────────────────────────────────────────────────

def _first_match(text: str, patterns: list[str], flags: int = re.IGNORECASE) -> Optional[str]:
    """Return the first captured group from the first matching pattern."""
    for pat in patterns:
        m = re.search(pat, text, flags)
        if m:
            return m.group(1).strip()
    return None

def _clean_number(raw: Optional[str]) -> Optional[float]:
    """Convert '123.456' or '123,456' (Argentine/European formatting) to float."""
    if not raw:
        return None
    # Remove thousands separators (. or ,) then normalise decimal comma → dot
    cleaned = raw.replace(".", "").replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None

def _safe_int(raw: Optional[str]) -> Optional[int]:
    v = _clean_number(raw)
    return int(v) if v is not None else None


# ── Per-field pattern lists ───────────────────────────────────────────────────
#  Each list is tried in order; the first match wins.
#  Spanish field labels are primary; English are fallbacks.

PATTERNS: dict[str, list[str]] = {
    # ── Identity ──────────────────────────────────────────────────────────────
    "marca": [
        r"(?:Marca|Brand)\s*[:\|]\s*([A-Za-z][A-Za-z0-9\s\-&\.]+?)(?:\n|\|)",
        r"\*\*(?:Marca|Brand)\*\*\s*[:\|]?\s*([A-Za-z][A-Za-z0-9\s\-&\.]+?)(?:\n|\*)",
    ],
    "modelo": [
        r"(?:Modelo|Model)\s*[:\|]\s*([A-Za-z0-9][A-Za-z0-9\s\-\/\.]+?)(?:\n|\|)",
        r"\*\*(?:Modelo|Model)\*\*\s*[:\|]?\s*([A-Za-z0-9][A-Za-z0-9\s\-\/\.]+?)(?:\n|\*)",
    ],
    "version": [
        r"(?:Versión|Version|Trim|Línea)\s*[:\|]\s*([^\n\|]{2,60})(?:\n|\|)",
        r"\*\*(?:Versión|Version)\*\*\s*[:\|]?\s*([^\n\*]{2,60})(?:\n|\*)",
    ],
    "anio": [
        r"(?:Año|Year)\s*[:\|]\s*(\d{4})\b",
        r"\b(20[0-2]\d|19[89]\d)\b",      # fallback: any plausible year in text
    ],

    # ── Condition & Usage ──────────────────────────────────────────────────────
    "kilometros": [
        r"(?:Kilómetros|Kilometros|km)\s*[:\|]\s*([\d\.]+)",
        r"([\d\.]+)\s*(?:km|kilómetros)\b",
    ],
    # condicion rarely appears as a field; derive from km in extract_features instead
    "condicion": [
        r"(?:Condición|Condicion|Condition)\s*[:\|]\s*(Usado|Nuevo|used|new)\b",
        r"\b(Usado|Nuevo)\b",
    ],

    # ── Powertrain ─────────────────────────────────────────────────────────────
    "cilindrada_cc": [
        # Explicit cc value
        r"(?:Cilindrada|Engine displacement)\s*[:\|]\s*([\d\.]+)\s*(?:cc|cm[³3])",
        r"(\d{3,4})\s*cc\b",
        # "Motor | 2.0" — liters; converted ×1000 to cc in extract_features
        r"(?:Motor)\s*[:\|]\s*([\d\.]+)\s*(?:\||$|\n)",
    ],
    "combustible": [
        r"(?:Combustible|Tipo de combustible|Fuel)\s*[:\|]\s*([A-Za-záéíóúüñÁÉÍÓÚÜÑ\s\/]+?)(?:\n|\|)",
        r"\b(Nafta|Diesel|Diésel|GNC|Eléctrico|Electrico|Híbrido|Hibrido|Gasoil)\b",
    ],
    "transmision": [
        r"(?:Transmisión|Transmision|Caja|Transmission)\s*[:\|]\s*([A-Za-záéíóúüñ\s]+?)(?:\n|\|)",
        r"\b(Manual|Automática|Automatica|CVT|Automático|Automatico)\b",
    ],
    "traccion": [
        # "Control de tracción | 4x2" is the actual ML table format
        r"(?:Control de tracción|Control de traccion|Tracción|Traccion|Traction)\s*[:\|]\s*([A-Za-z0-9x\/\s]+?)(?:\n|\|)",
        r"\b(Delantera|Trasera|4x4|4x2|AWD|4WD)\b",
    ],

    # ── Body & Exterior ────────────────────────────────────────────────────────
    "tipo_carroceria": [
        r"(?:Carrocería|Carroceria|Body type|Tipo de carrocería)\s*[:\|]\s*([A-Za-záéíóúüñÁÉÍÓÚÜÑ\-\s]+?)(?:\n|\|)",
        r"\b(Sedán|Sedan|Hatchback|SUV|Pick-Up|Pickup|Coupé|Coupe|Familiar|Monovolumen|Cabriolet|Furgón|Furgon)\b",
    ],
    "puertas": [
        r"(?:Puertas|Doors)\s*[:\|]\s*(\d)\b",
        r"(\d)\s*puertas\b",
    ],
    "color": [
        r"(?:Color)\s*[:\|]\s*([A-Za-záéíóúüñÁÉÍÓÚÜÑ\s]+?)(?:\n|\|)",
        r"\*\*Color\*\*\s*[:\|]?\s*([A-Za-záéíóúüñÁÉÍÓÚÜÑ\s]+?)(?:\n|\*)",
    ],

    # ── Pricing & Listing ──────────────────────────────────────────────────────
    "precio": [
        # "US$37.100" — actual ML format on item pages
        r"US\$\s*([\d\.,]+)",
        # "USD 12.500" or "U$S 12.500"
        r"(?:USD|U\$S|u\$s)\s*([\d\.,]+)",
        # "$ 12.500"
        r"\$\s*([\d\.,]+)",
        r"([\d\.,]+)\s*(?:USD|ARS|dólares|pesos)\b",
    ],
    "moneda": [
        r"(US\$)",                         # "US$37.100" — actual ML format → normalised to "USD"
        r"\b(USD|U\$S)\b",
        r"\b(ARS|pesos)\b",
        r"(dólares)",                      # → normalised to "USD" in post-process
    ],
    "es_concesionario": [
        # "Concesionario" / "Tienda oficial" / "vendedor particular"
        r"\b(Concesionario|Tienda oficial|vendedor oficial)\b",
        r"\b(particular|privado)\b",       # → 0 in post-process
    ],
    # ── Location ───────────────────────────────────────────────────────────────
    "provincia": [
        r"(?:Provincia|Province)\s*[:\|]\s*([A-Za-záéíóúüñÁÉÍÓÚÜÑ\s]+?)(?:\n|\|)",
        r"(?:ubicación|ubicacion|Ubicación)\s*[:\|]?\s*[A-Za-záéíóúüñ\s,]+?,\s*([A-Za-záéíóúüñÁÉÍÓÚÜÑ\s]+?)(?:\n|$)",
        # Fallback: known province/city names anywhere in text
        r"\b(Buenos Aires|CABA|Capital Federal|Ciudad Autónoma|Córdoba|Cordoba|Santa Fe|Mendoza|"
        r"Tucumán|Tucuman|Entre Ríos|Entre Rios|Salta|Misiones|Chaco|Corrientes|"
        r"Santiago del Estero|San Juan|Jujuy|Río Negro|Rio Negro|Neuquén|Neuquen|"
        r"Formosa|Chubut|San Luis|Catamarca|La Rioja|La Pampa|Santa Cruz|Tierra del Fuego)\b",
    ],
}


# ── Post-processing helpers ───────────────────────────────────────────────────

def _normalise_moneda(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip().upper()
    if raw in ("USD", "U$S", "US$", "DÓLARES", "DOLARES"):
        return "USD"
    if raw in ("ARS", "PESOS"):
        return "ARS"
    # regex captured the prefix only (e.g. "US$" from \bUS\$)
    if "US$" in raw or "USD" in raw or "U$S" in raw:
        return "USD"
    return raw

def _normalise_condicion(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    return "used" if raw.lower() in ("usado", "used") else "new"

def _normalise_es_concesionario(raw: Optional[str]) -> Optional[int]:
    if not raw:
        return None
    lower = raw.lower()
    if any(w in lower for w in ("concesionario", "oficial", "tienda")):
        return 1
    if any(w in lower for w in ("particular", "privado")):
        return 0
    return None

def _extract_item_id(url: str) -> Optional[str]:
    m = re.search(r"/(MLA-?\d+)", url)
    return m.group(1).replace("-", "") if m else None


# ── Main extraction function ──────────────────────────────────────────────────

def extract_features(markdown: str, source_url: str = "") -> dict:
    """
    Parse a scraped item page (markdown) and return a flat feature dict.
    Missing fields are set to None (will appear as NaN in pandas).
    """
    raw: dict[str, Optional[str]] = {
        field: _first_match(markdown, pats)
        for field, pats in PATTERNS.items()
    }

    current_year = datetime.now(timezone.utc).year

    anio_int     = _safe_int(raw["anio"])
    km_float     = _clean_number(raw["kilometros"])
    precio_float = _clean_number(raw["precio"])
    puertas_int  = _safe_int(raw["puertas"])
    edad         = (current_year - anio_int) if anio_int else None
    moneda       = _normalise_moneda(raw["moneda"])
    concesionario = _normalise_es_concesionario(raw["es_concesionario"])

    # km_por_anio: use `is not None` so km=0 (0km cars) still computes to 0.0
    km_por_anio = (
        round(km_float / edad, 1)
        if km_float is not None and edad and edad > 0
        else None
    )

    # condicion: derive from km when not explicit in the page
    condicion = _normalise_condicion(raw["condicion"])
    if condicion is None and km_float is not None:
        condicion = "new" if km_float == 0 else "used"

    # cilindrada_cc: explicit cc value OR Motor (liters) × 1000
    cc_raw = _clean_number(raw["cilindrada_cc"])
    if cc_raw is not None:
        # Heuristic: if value < 20 it was parsed as liters (e.g. 2.0), convert to cc
        cc_int = int(cc_raw * 1000) if cc_raw < 20 else int(cc_raw)
    else:
        cc_int = None

    return {
        "item_id":          _extract_item_id(source_url),
        "source_url":       source_url,
        # Identity
        "marca":            raw["marca"],
        "modelo":           raw["modelo"],
        "version":          raw["version"],
        "anio":             anio_int,
        # Condition & Usage
        "kilometros":       km_float,
        "condicion":        condicion,
        # Powertrain
        "cilindrada_cc":    cc_int,
        "combustible":      raw["combustible"],
        "transmision":      raw["transmision"],
        "traccion":         raw["traccion"],
        # Body & Exterior
        "tipo_carroceria":  raw["tipo_carroceria"],
        "puertas":          puertas_int,
        "color":            raw["color"],
        # Pricing & Listing
        "precio":           precio_float,
        "moneda":           moneda,
        "es_concesionario": concesionario,
        # Location
        "provincia":        raw["provincia"],
        # Derived (computed here for convenience)
        "vehiculo_edad":    edad,
        "km_por_anio":      km_por_anio,
        # Meta
        "scraped_at":       datetime.now(timezone.utc).isoformat(),
    }
