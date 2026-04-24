"""Hyperparameter tuning for the AVM quantile regression model.

Uses Optuna (TPE sampler + MedianPruner) to search structural LightGBM
params. Optimizes q50 CV MAE on the training split only — test set is
never touched. After running, paste the printed params into _build_model()
in train.py and retrain.

Usage:
    python tune.py                              # 75 trials (~30 min)
    python tune.py --n-trials 5                 # smoke test (~30 s)
    python tune.py --output-params best.json    # also write params to JSON
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import optuna
from lightgbm import LGBMRegressor, early_stopping
from sklearn.model_selection import KFold, train_test_split

# Add ml_model/ to path so relative imports from train.py work when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from features import CATEGORICAL_FEATURES, TARGET, prepare_features
from train import DB_PATH, load_data

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)
optuna.logging.set_verbosity(optuna.logging.WARNING)

_QUANTILE = 0.5
_N_FOLDS = 5
_LEARNING_RATE = 0.05
_N_ESTIMATORS_CEILING = 2000
_EARLY_STOPPING_ROUNDS = 50
_TEST_SIZE = 0.2
_RANDOM_STATE = 42


def _objective(trial: optuna.Trial, X: "pd.DataFrame", y: "pd.Series") -> float:
    params = {
        "num_leaves":        trial.suggest_int("num_leaves", 20, 150),
        "min_child_samples": trial.suggest_int("min_child_samples", 5, 60),
        "max_depth":         trial.suggest_categorical("max_depth", [-1, 6, 8, 10, 12]),
        "min_split_gain":    trial.suggest_float("min_split_gain", 0.0, 0.5),
        "subsample":         trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree":  trial.suggest_float("colsample_bytree", 0.6, 1.0),
        "reg_alpha":         trial.suggest_float("reg_alpha", 1e-4, 1.0, log=True),
        "reg_lambda":        trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
    }
    # subsample only activates when subsample_freq > 0
    subsample_freq = 1 if params["subsample"] < 1.0 else 0

    kf = KFold(n_splits=_N_FOLDS, shuffle=True, random_state=_RANDOM_STATE)
    fold_maes: list[float] = []
    best_iterations: list[int] = []

    for fold, (train_idx, val_idx) in enumerate(kf.split(X)):
        X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]

        model = LGBMRegressor(
            objective="quantile",
            alpha=_QUANTILE,
            n_estimators=_N_ESTIMATORS_CEILING,
            learning_rate=_LEARNING_RATE,
            subsample_freq=subsample_freq,
            random_state=_RANDOM_STATE,
            verbose=-1,
            **params,
        )
        model.fit(
            X_tr, y_tr,
            categorical_feature=CATEGORICAL_FEATURES,
            eval_set=[(X_val, y_val)],
            callbacks=[early_stopping(_EARLY_STOPPING_ROUNDS, verbose=False)],
        )

        y_pred_log = model.predict(X_val)
        fold_mae = float(np.mean(np.abs(np.exp(y_val) - np.exp(y_pred_log))))
        fold_maes.append(fold_mae)
        best_iterations.append(model.best_iteration_)

        # Report intermediate value for pruner
        trial.report(float(np.mean(fold_maes)), fold)
        if trial.should_prune():
            raise optuna.TrialPruned()

    trial.set_user_attr("mean_best_iteration", int(np.mean(best_iterations)))
    return float(np.mean(fold_maes))


def tune(db_path: Path = DB_PATH, n_trials: int = 75, output_params: Path | None = None) -> dict:
    df = load_data(db_path)
    X = prepare_features(df)
    y = np.log(df[TARGET])

    # Mirror the exact split from train.py so CV never sees the held-out test rows
    X_train, _, y_train, _ = train_test_split(
        X, y, test_size=_TEST_SIZE, random_state=_RANDOM_STATE,
    )
    log.info("Tuning on %d training rows (%d held-out test rows excluded)", len(X_train), len(_))

    pruner = optuna.pruners.MedianPruner(n_startup_trials=10, n_warmup_steps=2)
    study = optuna.create_study(direction="minimize", pruner=pruner)
    study.optimize(
        lambda trial: _objective(trial, X_train, y_train),
        n_trials=n_trials,
        show_progress_bar=True,
    )

    best = study.best_trial
    mean_best_iter = best.user_attrs.get("mean_best_iteration", 300)
    recommended_n_estimators = round(mean_best_iter * 1.1)

    print(f"\nBest CV MAE: ${best.value:,.2f}  ({n_trials} trials, baseline $2,054)")
    print("Paste into _build_model() in train.py:")
    for k, v in best.params.items():
        print(f"  {k}={v!r}")
    print(f"  n_estimators={recommended_n_estimators}  # early stopping mean ({mean_best_iter}) × 1.1")
    print(f"  learning_rate={_LEARNING_RATE}")

    result = dict(best.params)
    result["n_estimators"] = recommended_n_estimators
    result["learning_rate"] = _LEARNING_RATE

    if output_params is not None:
        output_params.write_text(json.dumps(result, indent=2))
        print(f"Params written to {output_params}")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune AVM hyperparameters with Optuna")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Path to SQLite DB")
    parser.add_argument("--n-trials", type=int, default=75, help="Number of Optuna trials")
    parser.add_argument("--output-params", type=Path, default=None,
                        help="Optional JSON file to write best params to")
    args = parser.parse_args()

    tune(db_path=args.db, n_trials=args.n_trials, output_params=args.output_params)


if __name__ == "__main__":
    main()
