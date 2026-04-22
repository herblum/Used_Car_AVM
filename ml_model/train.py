"""Train quantile-regression models for car price prediction.

Trains three LightGBM models (10th, 50th, 90th percentile) and saves
them as a single .joblib artifact. Uses a held-out test set for final
evaluation and k-fold CV on the training set for development metrics.
"""

import argparse
import logging
import sqlite3
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.model_selection import KFold, train_test_split

from evaluate import evaluate_model
from features import ALL_FEATURES, ARS_TO_USD, CATEGORICAL_FEATURES, TARGET, prepare_features

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "avm.db"
MODEL_DIR = Path(__file__).resolve().parent / "artifacts"
QUANTILES = [0.1, 0.5, 0.9]
N_FOLDS = 5
TEST_SIZE = 0.2


def load_data(db_path: Path = DB_PATH) -> pd.DataFrame:
    """Load listings from SQLite and apply minimal cleaning."""
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM listings", conn)
    conn.close()

    # Drop rows without a price
    df = df.dropna(subset=[TARGET])

    # Fix mislabeled currencies: any price > 500K is ARS regardless of label
    mislabeled = (df["precio"] > 500_000) & (df["moneda"] != "ARS")
    df.loc[mislabeled, "moneda"] = "ARS"
    log.info("Corrected %d mislabeled currency rows", mislabeled.sum())

    # Infer missing currency from price magnitude
    null_ars = df["moneda"].isna() & (df["precio"] > 500_000)
    df.loc[null_ars, "moneda"] = "ARS"

    # Remaining nulls with low prices are assumed USD
    df.loc[df["moneda"].isna(), "moneda"] = "USD"

    # Normalize all prices to USD
    ars_mask = df["moneda"] == "ARS"
    df.loc[ars_mask, "precio"] = df.loc[ars_mask, "precio"] * ARS_TO_USD
    log.info("Converted %d ARS prices to USD (rate: 1 USD = %d ARS)", ars_mask.sum(), int(1 / ARS_TO_USD))

    # Remove price outliers via IQR
    q1 = df["precio"].quantile(0.25)
    q3 = df["precio"].quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    before = len(df)
    df = df[(df["precio"] >= lower) & (df["precio"] <= upper)]
    log.info("IQR filter: removed %d outliers (bounds: $%.0f – $%.0f)", before - len(df), lower, upper)

    log.info("Loaded %d rows (%d features)", len(df), len(ALL_FEATURES))
    return df


def _build_model(quantile: float) -> LGBMRegressor:
    return LGBMRegressor(
        objective="quantile",
        alpha=quantile,
        n_estimators=300,
        num_leaves=31,
        learning_rate=0.05,
        min_child_samples=5,
        random_state=42,
        verbose=-1,
    )


def cross_validate(X: pd.DataFrame, y: pd.Series) -> None:
    """Run k-fold CV on the median model (q50) and log aggregated metrics."""
    kf = KFold(n_splits=N_FOLDS, shuffle=True, random_state=42)
    all_y_true, all_y_pred = [], []

    for fold, (train_idx, val_idx) in enumerate(kf.split(X), 1):
        X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]

        model = _build_model(0.5)
        model.fit(X_tr, y_tr, categorical_feature=CATEGORICAL_FEATURES)

        all_y_true.append(y_val)
        all_y_pred.append(model.predict(X_val))

    y_true_all = pd.concat(all_y_true)
    y_pred_all = np.concatenate(all_y_pred)

    log.info("--- %d-fold CV on training set (q50) ---", N_FOLDS)
    evaluate_model(np.exp(y_true_all), np.exp(y_pred_all), label=f"CV-{N_FOLDS}fold")


def train(db_path: Path = DB_PATH, output_dir: Path = MODEL_DIR) -> Path:
    """Train quantile models with CV + held-out test evaluation.

    1. Split data into train (80%) and test (20%) — test is never touched during CV.
    2. Run k-fold CV on the training set for development metrics.
    3. Train final models on the full training set.
    4. Evaluate final models on the held-out test set.
    5. Save the artifact.

    Returns the path to the saved .joblib file.
    """
    df = load_data(db_path)

    X = prepare_features(df)
    y = np.log(df[TARGET])

    # 1. Hold out test set
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=42,
    )
    log.info("Train: %d rows, Test (held-out): %d rows", len(X_train), len(X_test))

    # 2. Cross-validation on training set only
    cross_validate(X_train, y_train)

    # 3. Train final models on full training set
    log.info("--- Training final models on training set (%d rows) ---", len(X_train))
    models = {}
    for q in QUANTILES:
        label = f"q{int(q * 100)}"
        log.info("Training %s...", label)
        model = _build_model(q)
        model.fit(X_train, y_train, categorical_feature=CATEGORICAL_FEATURES)
        models[label] = model

    # 4. Evaluate all quantiles on held-out test set
    log.info("--- Held-out test set evaluation ---")
    for label, model in models.items():
        y_pred = model.predict(X_test)
        evaluate_model(np.exp(y_test), np.exp(y_pred), label=f"test-{label}")

    # 5. Save
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / "avm_model.joblib"
    joblib.dump(models, artifact_path)
    log.info("Model saved to %s (%.2f MB)", artifact_path, artifact_path.stat().st_size / 1e6)

    return artifact_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the AVM price model")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Path to SQLite DB")
    parser.add_argument("--output", type=Path, default=MODEL_DIR, help="Output directory")
    args = parser.parse_args()

    train(db_path=args.db, output_dir=args.output)


if __name__ == "__main__":
    main()
