"""Pedido sugerido a partir del pronóstico y los costos de negocio (problema del newsvendor).

Si pedir una unidad de menos cuesta ``Cu`` (quiebre) y una de más cuesta ``Co`` (merma), la cantidad
que minimiza el costo esperado es el cuantil ``q* = Cu / (Cu + Co)`` de la demanda. Con los costos
de ``config/business_costs.yaml`` (0.30 y 0.10), ``q* = 0.75``.

El modelo pronostica la venta esperada; para pasar a un cuantil se calibra, por familia, un factor
``k`` en la ventana de validación y el pedido es ``k * pronóstico`` redondeado al entero más
cercano (DECISIONES.md, D9).

Con pedido ``k * p`` y venta real ``r = x * p``, el costo de una fila es
``p * [Co * (k - x)+ + Cu * (x - k)+]``. La suma se minimiza con el cuantil ``q*`` de ``x``
ponderado por ``p``: las filas de mayor volumen pesan más, como en el costo real.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from motor_reposicion.configuracion import Costos


def cuantil_ponderado(valores: np.ndarray, pesos: np.ndarray, q: float) -> float:
    """Cuantil ``q`` de ``valores`` con ``pesos`` (menor valor cuya masa acumulada alcanza q)."""
    valores = np.asarray(valores, dtype="float64")
    pesos = np.asarray(pesos, dtype="float64")
    if len(valores) == 0 or pesos.sum() <= 0:
        raise ValueError("Se necesitan valores con peso positivo")
    orden = np.argsort(valores, kind="mergesort")
    acumulado = np.cumsum(pesos[orden]) / pesos.sum()
    return float(valores[orden][np.searchsorted(acumulado, q, side="left")])


def calibrar_factores(
    familias: pd.Series,
    real: np.ndarray,
    pronostico: np.ndarray,
    costos: Costos,
) -> dict[str, float]:
    """Factor por familia que lleva el pronóstico al cuantil óptimo del newsvendor."""
    df = pd.DataFrame({"family": familias.to_numpy(), "real": real, "pred": pronostico})
    df = df[np.isfinite(df["real"]) & (df["pred"] > 0.5)]
    df["x"] = df["real"] / df["pred"]
    minimo, maximo = costos.limites_factor
    q = costos.cuantil_optimo
    global_ = cuantil_ponderado(df["x"], df["pred"], q) if len(df) else 1.0
    factores = {}
    for familia, grupo in df.groupby("family"):
        valor = cuantil_ponderado(grupo["x"], grupo["pred"], q) if len(grupo) >= 30 else global_
        factores[str(familia)] = float(np.clip(valor, minimo, maximo))
    factores["__global__"] = float(np.clip(global_, minimo, maximo))
    return factores


def calcular_pedido(
    familias: pd.Series,
    pronostico: np.ndarray,
    factores: dict[str, float],
) -> np.ndarray:
    """Unidades a pedir: ``factor_familia * pronóstico`` redondeado al entero más cercano.

    Se redondea y no se usa el techo para no pedir una unidad diaria de productos cuyo pronóstico
    es casi cero (con el techo, 0.05 unidades esperadas se volvían 1 unidad cada día).
    """
    por_defecto = factores.get("__global__", 1.0)
    k = familias.map(lambda f: factores.get(str(f), por_defecto)).to_numpy(dtype="float64")
    valores = np.clip(np.asarray(pronostico, dtype="float64"), 0, None) * k
    return np.floor(np.round(valores, 6) + 0.5).astype("int64")


def costo_pedido(real: np.ndarray, pedido: np.ndarray, costos: Costos) -> dict[str, float]:
    """Costo de merma (pedido > real) y de quiebre (pedido < real)."""
    real = np.asarray(real, dtype="float64")
    pedido = np.asarray(pedido, dtype="float64")
    sobrante = np.clip(pedido - real, 0, None).sum()
    faltante = np.clip(real - pedido, 0, None).sum()
    merma = float(sobrante * costos.merma)
    quiebre = float(faltante * costos.quiebre)
    return {
        "costo_merma": round(merma, 2),
        "costo_quiebre": round(quiebre, 2),
        "costo_total": round(merma + quiebre, 2),
        "unidades_sobrantes": round(float(sobrante), 1),
        "unidades_faltantes": round(float(faltante), 1),
    }


def pedido_semanal(pronostico: pd.DataFrame, corte: pd.Timestamp, dias: int) -> pd.DataFrame:
    """Suma, por tienda y familia, la venta esperada y el pedido de los ``dias`` siguientes."""
    corte = pd.Timestamp(corte)
    semana = pronostico[(pronostico["date"] > corte)
                        & (pronostico["date"] <= corte + pd.Timedelta(days=dias))]
    resumen = (
        semana.groupby(["store_nbr", "family"], as_index=False)
        .agg(venta_esperada=("venta_esperada", "sum"), pedido_sugerido=("pedido_sugerido", "sum"))
    )
    resumen["venta_esperada"] = resumen["venta_esperada"].round(1)
    resumen.insert(0, "semana_desde", f"{corte + pd.Timedelta(days=1):%Y-%m-%d}")
    resumen.insert(1, "semana_hasta", f"{corte + pd.Timedelta(days=dias):%Y-%m-%d}")
    return resumen
