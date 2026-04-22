"""Feature definitions and preprocessing for the AVM model.

LightGBM handles nulls and categorical features natively, so preprocessing
is minimal: just select columns and set correct dtypes.
"""

import pandas as pd

NUMERIC_FEATURES = [
    "anio",
    "kilometros",
    "vehiculo_edad",
    "cilindrada_cc",
    "puertas",
    "km_por_anio",
    "es_concesionario",
]

CATEGORICAL_FEATURES = [
    "marca",
    "modelo",
    "condicion",
    "combustible",
    "transmision",
    "traccion",
    "tipo_carroceria",
    "color",
    "provincia",
    "trim_level",
]

# All prices are normalized to USD before training
ARS_TO_USD = 1 / 1400

ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

TARGET = "precio"


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Select feature columns and set dtypes for LightGBM.

    - Numeric columns stay as-is (LightGBM handles NaN natively).
    - Categorical columns are cast to pandas 'category' dtype so LightGBM
      uses its native categorical split algorithm (no encoding needed).
    - trim_level is extracted from the version column when available (training);
      at inference time the column is absent and LightGBM handles it as missing.
    """
    from trim_extractor import extract_trim

    df = df.copy()

    if "version" in df.columns:
        df["trim_level"] = df.apply(
            lambda row: extract_trim(row.get("version"), row.get("marca"), row.get("modelo")),
            axis=1,
        )
    elif "trim_level" not in df.columns:
        df["trim_level"] = None

    X = df[ALL_FEATURES].copy()
    for col in NUMERIC_FEATURES:
        X[col] = pd.to_numeric(X[col], errors="coerce")
    for col in CATEGORICAL_FEATURES:
        X[col] = X[col].astype("category")
    return X
