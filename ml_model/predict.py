"""Inference function for the AVM model.

Loads a trained .joblib artifact (three quantile models) and returns
a price range for a given set of car features. The model predicts in
USD internally; output is converted to the user's requested currency.
"""

import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from features import ALL_FEATURES, ARS_TO_USD, prepare_features

log = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).resolve().parent / "artifacts" / "avm_model.joblib"

_cached_models: dict | None = None


def _load_models(model_path: Path = MODEL_PATH) -> dict:
    """Load models from disk, caching in memory for repeated calls."""
    global _cached_models
    if _cached_models is None:
        _cached_models = joblib.load(model_path)
        log.info("Loaded model from %s", model_path)
    return _cached_models


def predict(features: dict, model_path: Path = MODEL_PATH) -> dict:
    """Predict a price range for a single car.

    Args:
        features: Dict with keys matching ALL_FEATURES (e.g. marca, modelo,
                  anio, kilometros, ...). Missing keys become NaN.
                  "moneda" controls output currency (default "USD").
        model_path: Path to the .joblib artifact.

    Returns:
        {
            "price_low":  float,  # 10th percentile
            "price_mid":  float,  # 50th percentile (median)
            "price_high": float,  # 90th percentile
            "currency":   str,    # requested currency
        }
    """
    models = _load_models(model_path)
    currency = features.get("moneda", "USD")

    # Build a single-row DataFrame with the expected columns
    row = {col: features.get(col) for col in ALL_FEATURES}
    df = pd.DataFrame([row])
    X = prepare_features(df)

    # Model predicts log(USD); exponentiate back to USD
    low  = max(0.0, float(np.exp(models["q10"].predict(X)[0])))
    mid  = max(0.0, float(np.exp(models["q50"].predict(X)[0])))
    high = max(0.0, float(np.exp(models["q90"].predict(X)[0])))

    # Convert to requested currency
    if currency == "ARS":
        rate = 1 / ARS_TO_USD
        low, mid, high = low * rate, mid * rate, high * rate

    return {
        "price_low": round(low, 2),
        "price_mid": round(mid, 2),
        "price_high": round(high, 2),
        "currency": currency,
    }
