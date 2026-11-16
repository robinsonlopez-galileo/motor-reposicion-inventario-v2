"""Entrenamiento del candidato y evaluación en la ventana de validación temporal.

Para un corte ``c`` (DECISIONES.md, D8):

- Validación: los ``validation_days`` días que terminan en ``c``.
- Entrenamiento: los ``training_window_days`` días anteriores a la validación.

Candidato, baseline y modelo vigente se evalúan sobre las mismas filas de validación, que ninguno
de ellos vio al entrenar (el vigente se entrenó con un corte anterior y, por lo tanto, con datos
todavía más antiguos).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from motor_reposicion.configuracion import Costos, ParametrosModelo
from motor_reposicion.features import columnas_modelo
from motor_reposicion.modelo.estimadores import ModeloBaseline, ModeloBoosting
from motor_reposicion.modelo.metricas import metricas_tecnicas
from motor_reposicion.pedido import calcular_pedido, calibrar_factores, costo_pedido


def dividir(
    dataset: pd.DataFrame, params: ParametrosModelo
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Separa entrenamiento, validación y horizonte futuro sin mezclar fechas."""
    corte = pd.Timestamp(dataset["corte"].iloc[0])
    fin_entrenamiento = corte - pd.Timedelta(days=params.dias_validacion)
    inicio = fin_entrenamiento - pd.Timedelta(days=params.ventana_entrenamiento - 1)
    conocido = dataset[
        (dataset["es_futuro"] == 0) & dataset["sales"].notna() & (dataset["tienda_cerrada"] == 0)
    ]
    entrenamiento = conocido[(conocido["date"] >= inicio) & (conocido["date"] <= fin_entrenamiento)]
    validacion = conocido[conocido["date"] > fin_entrenamiento]
    futuro = dataset[dataset["es_futuro"] == 1]
    return entrenamiento, validacion, futuro


def evaluar(modelo, validacion: pd.DataFrame, costos: Costos) -> tuple[dict, dict[str, float]]:
    """Métricas técnicas y de negocio de un modelo en la validación.

    El factor del pedido se calibra en la misma ventana para todos los modelos comparados, de
    modo que la comparación mide la calidad del pronóstico y no la del factor.
    """
    real = validacion["sales"].to_numpy(dtype="float64")
    pronostico = modelo.predecir(validacion)
    factores = calibrar_factores(validacion["family"], real, pronostico, costos)
    pedido = calcular_pedido(validacion["family"], pronostico, factores)
    metricas = {**metricas_tecnicas(real, pronostico), **costo_pedido(real, pedido, costos)}
    return metricas, factores


@dataclass
class ResultadoEntrenamiento:
    candidato: ModeloBoosting
    baseline: ModeloBaseline
    metricas_candidato: dict
    metricas_baseline: dict
    validacion_desde: str
    validacion_hasta: str
    filas_entrenamiento: int

    def resumen(self) -> dict:
        return {
            "validacion": [self.validacion_desde, self.validacion_hasta],
            "filas_entrenamiento": self.filas_entrenamiento,
            "candidato": self.metricas_candidato,
            "baseline": self.metricas_baseline,
        }


def entrenar_candidato(
    dataset: pd.DataFrame, params: ParametrosModelo, costos: Costos
) -> ResultadoEntrenamiento:
    entrenamiento, validacion, _ = dividir(dataset, params)
    if entrenamiento.empty or validacion.empty:
        raise ValueError("No hay suficientes datos para entrenar y validar en este corte")
    candidato = ModeloBoosting(params.hiperparametros, columnas_modelo(params)).ajustar(
        entrenamiento)
    metricas_c, factores_c = evaluar(candidato, validacion, costos)
    candidato.factores = factores_c

    baseline = ModeloBaseline(params.semanas_baseline).ajustar(entrenamiento)
    metricas_b, factores_b = evaluar(baseline, validacion, costos)
    baseline.factores = factores_b

    return ResultadoEntrenamiento(
        candidato=candidato,
        baseline=baseline,
        metricas_candidato=metricas_c,
        metricas_baseline=metricas_b,
        validacion_desde=f"{validacion['date'].min():%Y-%m-%d}",
        validacion_hasta=f"{validacion['date'].max():%Y-%m-%d}",
        filas_entrenamiento=int(len(entrenamiento)),
    )


def evaluar_vigente(modelo, dataset: pd.DataFrame, params: ParametrosModelo,
                    costos: Costos) -> tuple[dict, dict[str, float]] | None:
    """Métricas y factores recalibrados del vigente en la validación de este corte.

    Devuelve ``None`` si el vigente no se puede evaluar (por ejemplo, usa variables que ya no se
    construyen porque cambió la configuración).
    """
    _, validacion, _ = dividir(dataset, params)
    faltantes = [c for c in getattr(modelo, "columnas", []) if c not in validacion.columns]
    if faltantes or validacion.empty:
        return None
    return evaluar(modelo, validacion, costos)


def predecir_horizonte(modelo, futuro: pd.DataFrame) -> np.ndarray:
    return modelo.predecir(futuro)
