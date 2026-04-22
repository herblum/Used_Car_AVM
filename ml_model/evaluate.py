"""Model evaluation metrics for the AVM model."""

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def evaluate_model(
    y_true: pd.Series,
    y_pred: np.ndarray,
    label: str = "q50",
) -> dict[str, float]:
    """Compute regression metrics and log them.

    Returns a dict with MAE, RMSE, MAPE, and R².
    """
    errors = y_true.values - y_pred
    mae = np.mean(np.abs(errors))
    rmse = np.sqrt(np.mean(errors ** 2))
    ss_res = np.sum(errors ** 2)
    ss_tot = np.sum((y_true.values - y_true.mean()) ** 2)
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    # MAPE — skip zeros to avoid division errors
    nonzero = y_true.values != 0
    mape = np.mean(np.abs(errors[nonzero] / y_true.values[nonzero])) * 100

    metrics = {"MAE": mae, "RMSE": rmse, "R2": r2, "MAPE": mape}
    log.info(
        "[%s] MAE=%.2f  RMSE=%.2f  R²=%.4f  MAPE=%.2f%%",
        label, mae, rmse, r2, mape,
    )
    return metrics
