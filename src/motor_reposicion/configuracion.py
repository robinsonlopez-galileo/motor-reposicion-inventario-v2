"""Rutas y parámetros del motor de reposición.

Todo lo configurable vive en ``config/*.yaml``; las rutas se pueden cambiar con variables de
entorno para que el mismo código corra en la laptop, en Docker y en las pruebas.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Rutas:
    """Carpetas de trabajo del motor."""

    datos: Path
    kaggle: Path
    config: Path

    @property
    def raw(self) -> Path:
        return self.datos / "raw"

    @property
    def inbox(self) -> Path:
        return self.datos / "inbox"

    @property
    def processed(self) -> Path:
        return self.datos / "processed"

    @property
    def forecasts(self) -> Path:
        return self.datos / "forecasts"

    @property
    def reports(self) -> Path:
        return self.datos / "reports"

    @property
    def models(self) -> Path:
        return self.datos / "models"

    @property
    def control(self) -> Path:
        return self.datos / "control"


def rutas_desde_entorno() -> Rutas:
    """Rutas por defecto del repositorio, sobrescribibles con MOTOR_DATA_DIR, MOTOR_KAGGLE_DIR y
    MOTOR_CONFIG_DIR."""
    return Rutas(
        datos=Path(os.environ.get("MOTOR_DATA_DIR", RAIZ_PROYECTO / "data")),
        kaggle=Path(os.environ.get("MOTOR_KAGGLE_DIR", RAIZ_PROYECTO / "datos" / "kaggle")),
        config=Path(os.environ.get("MOTOR_CONFIG_DIR", RAIZ_PROYECTO / "config")),
    )


def _leer_yaml(ruta: Path) -> dict[str, Any]:
    with open(ruta, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@dataclass(frozen=True)
class Operacion:
    """Periodo de operación simulado."""

    corte_historico: pd.Timestamp
    fin_operacion: pd.Timestamp
    fuentes_bandeja: tuple[str, ...]

    @property
    def inicio(self) -> pd.Timestamp:
        """Primer día de la bandeja."""
        return self.corte_historico + pd.Timedelta(days=1)

    def dias(self) -> pd.DatetimeIndex:
        return pd.date_range(self.inicio, self.fin_operacion, freq="D")

    def lunes(self) -> pd.DatetimeIndex:
        """Cortes semanales (lunes) dentro del periodo de operación."""
        return pd.date_range(self.inicio, self.fin_operacion, freq="W-MON")


def cargar_operacion(rutas: Rutas | None = None) -> Operacion:
    rutas = rutas or rutas_desde_entorno()
    cfg = _leer_yaml(rutas.config / "operacion.yaml")
    corte = pd.Timestamp(os.environ.get("CORTE_HISTORICO") or cfg["corte_historico"])
    fin = pd.Timestamp(os.environ.get("FIN_OPERACION") or cfg["fin_operacion"])
    if fin <= corte:
        raise ValueError(
            f"fin_operacion ({fin.date()}) debe ser posterior al corte ({corte.date()})")
    fuentes = tuple(cfg.get("fuentes_bandeja", ["ventas", "oil", "transactions"]))
    return Operacion(corte, fin, fuentes)


@dataclass(frozen=True)
class Costos:
    quiebre: float
    merma: float
    horizonte: int
    dias_pedido: int
    limites_factor: tuple[float, float] = (0.5, 3.0)

    @property
    def cuantil_optimo(self) -> float:
        """Cuantil del newsvendor: q* = Cu / (Cu + Co)."""
        return self.quiebre / (self.quiebre + self.merma)


def cargar_costos(rutas: Rutas | None = None) -> Costos:
    rutas = rutas or rutas_desde_entorno()
    cfg = _leer_yaml(rutas.config / "business_costs.yaml")
    costos = cfg["costs"]
    limites = cfg.get("order_factor_bounds", [0.5, 3.0])
    resultado = Costos(
        quiebre=float(costos["stockout_cost_per_unit"]),
        merma=float(costos["waste_cost_per_unit"]),
        horizonte=int(cfg["forecast_horizon_days"]),
        dias_pedido=int(cfg.get("order_days", 7)),
        limites_factor=(float(limites[0]), float(limites[1])),
    )
    if resultado.quiebre <= 0 or resultado.merma <= 0:
        raise ValueError("Los costos de quiebre y merma deben ser positivos")
    if not 1 <= resultado.dias_pedido <= resultado.horizonte:
        raise ValueError("order_days debe estar entre 1 y forecast_horizon_days")
    return resultado


@dataclass(frozen=True)
class ParametrosModelo:
    hiperparametros: dict[str, Any]
    ventana_entrenamiento: int
    dias_validacion: int
    lags: tuple[int, ...]
    ventanas: tuple[int, ...]
    semanas_baseline: int
    metrica_reemplazo: str
    mejora_minima_pct: float
    extra: dict[str, Any] = field(default_factory=dict)


def cargar_parametros(rutas: Rutas | None = None, horizonte: int | None = None) -> ParametrosModelo:
    rutas = rutas or rutas_desde_entorno()
    cfg = _leer_yaml(rutas.config / "model_params.yaml")
    horizonte = horizonte if horizonte is not None else cargar_costos(rutas).horizonte
    lags = tuple(int(x) for x in cfg["features"]["lags"])
    if min(lags) < horizonte:
        raise ValueError(
            f"Los rezagos {lags} deben ser >= horizonte ({horizonte}) para no usar ventas futuras"
        )
    return ParametrosModelo(
        hiperparametros=dict(cfg["modelo"]),
        ventana_entrenamiento=int(cfg["training_window_days"]),
        dias_validacion=int(cfg["validation_days"]),
        lags=lags,
        ventanas=tuple(int(x) for x in cfg["features"]["rolling_windows"]),
        semanas_baseline=int(cfg["baseline"]["rolling_weeks"]),
        metrica_reemplazo=str(cfg["replacement"]["metric"]),
        mejora_minima_pct=float(cfg["replacement"]["min_improvement_pct"]),
    )
