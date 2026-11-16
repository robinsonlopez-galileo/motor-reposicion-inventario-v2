"""Modelos de pronóstico: baseline estadístico y gradient boosting.

Los dos exponen la misma interfaz (``predecir``), guardan la lista de variables que usan y los
factores por familia que convierten la venta esperada en pedido (``pedido.py``).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from motor_reposicion.features import COLUMNAS_CATEGORICAS


@dataclass
class ModeloBaseline:
    """Promedio de las últimas N semanas del mismo día de la semana (sin entrenamiento).

    Usa la columna ``baseline_misma_dia`` que construye ``features.py`` con la misma regla de
    información que el modelo de machine learning.
    """

    semanas: int = 8
    factores: dict[str, float] = field(default_factory=dict)
    entrenado_hasta: str | None = None
    tipo: str = "baseline"

    def ajustar(self, df: pd.DataFrame) -> ModeloBaseline:
        self.entrenado_hasta = f"{pd.Timestamp(df['date'].max()):%Y-%m-%d}"
        return self

    def predecir(self, df: pd.DataFrame) -> np.ndarray:
        return df["baseline_misma_dia"].fillna(0.0).clip(lower=0).to_numpy(dtype="float64")


@dataclass
class ModeloBoosting:
    """HistGradientBoostingRegressor con pérdida Poisson sobre las variables de ``features.py``."""

    hiperparametros: dict
    columnas: list[str]
    factores: dict[str, float] = field(default_factory=dict)
    entrenado_hasta: str | None = None
    tipo: str = "boosting"
    _modelo: HistGradientBoostingRegressor | None = None

    def ajustar(self, df: pd.DataFrame) -> ModeloBoosting:
        categoricas = [c for c in self.columnas if c in COLUMNAS_CATEGORICAS]
        self._modelo = HistGradientBoostingRegressor(
            categorical_features=categoricas, **self.hiperparametros
        )
        self._modelo.fit(df[self.columnas], df["sales"].to_numpy(dtype="float64"))
        self.entrenado_hasta = f"{pd.Timestamp(df['date'].max()):%Y-%m-%d}"
        return self

    def predecir(self, df: pd.DataFrame) -> np.ndarray:
        if self._modelo is None:
            raise RuntimeError("El modelo no está entrenado")
        return np.clip(self._modelo.predict(df[self.columnas]), 0, None)
