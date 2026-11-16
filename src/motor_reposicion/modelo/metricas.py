"""Métricas técnicas del pronóstico."""
from __future__ import annotations

import numpy as np


def metricas_tecnicas(real: np.ndarray, pronostico: np.ndarray) -> dict[str, float]:
    """MAE, RMSE y WAPE (error absoluto total / venta total)."""
    real = np.asarray(real, dtype="float64")
    pronostico = np.asarray(pronostico, dtype="float64")
    mascara = np.isfinite(real)
    real, pronostico = real[mascara], pronostico[mascara]
    if len(real) == 0:
        return {"MAE": float("nan"), "RMSE": float("nan"), "WAPE": float("nan"), "n": 0}
    error = pronostico - real
    total = np.abs(real).sum()
    return {
        "MAE": round(float(np.abs(error).mean()), 4),
        "RMSE": round(float(np.sqrt((error**2).mean())), 4),
        "WAPE": round(float(np.abs(error).sum() / total), 4) if total > 0 else float("nan"),
        "n": int(len(real)),
    }
