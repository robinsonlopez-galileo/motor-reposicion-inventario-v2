"""Variables del modelo, construidas con la información disponible al cierre del corte.

Regla central (DECISIONES.md, D4): cada fila de fecha ``t`` solo usa ventas, petróleo y
transacciones hasta ``t - horizonte``. Así, para cualquier día del horizonte (corte + 1 ... corte +
16) las variables usan solo datos hasta el corte, y las filas de entrenamiento se construyen con
exactamente la misma regla: no hay diferencia entre entrenar y predecir.

El calendario (día de la semana, feriados) sí se usa para la fecha objetivo, porque se conoce con
anticipación.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

from motor_reposicion.configuracion import ParametrosModelo, Rutas
from motor_reposicion.ingesta import almacen

COLUMNAS_CATEGORICAS = ["store_nbr", "familia_cod", "cluster", "tipo_tienda"]
COLUMNAS_CALENDARIO = [
    "dia_semana", "dia_mes", "mes", "semana_anio", "es_fin_semana", "dia_pago",
    "feriado_nacional", "feriado_regional", "feriado_local", "evento_nacional", "dia_laboral",
]
TIPOS_TIENDA = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}
TIPOS_FERIADO = {"Holiday", "Transfer", "Additional", "Bridge"}


@dataclass
class Fuentes:
    """Datos conocidos al cierre de un corte."""

    corte: pd.Timestamp
    ventas: pd.DataFrame
    oil: pd.DataFrame
    transactions: pd.DataFrame
    feriados: pd.DataFrame
    tiendas: pd.DataFrame
    familias: list[str]


def cargar_fuentes(rutas: Rutas, corte: pd.Timestamp | str) -> Fuentes:
    """Lee lo que se conocía al cierre de ``corte`` (entregas recibidas hasta ese día)."""
    corte = pd.Timestamp(corte).normalize()
    return Fuentes(
        corte=corte,
        ventas=almacen.leer_fuente(rutas.raw, "ventas", hasta=corte),
        oil=almacen.leer_fuente(rutas.raw, "oil", hasta=corte),
        transactions=almacen.leer_fuente(rutas.raw, "transactions", hasta=corte),
        feriados=almacen.leer_catalogo(rutas.raw, "holidays_events"),
        tiendas=almacen.leer_catalogo(rutas.raw, "stores"),
        familias=sorted(almacen.leer_catalogo(rutas.raw, "familias")["family"].astype(str)),
    )


def columnas_modelo(params: ParametrosModelo) -> list[str]:
    """Columnas que recibe el modelo, en orden fijo."""
    rezagos = [f"lag_{k}" for k in params.lags]
    medias = [f"media_{w}" for w in params.ventanas]
    return (
        COLUMNAS_CATEGORICAS
        + rezagos
        + medias
        + ["proporcion_ceros_28", "baseline_misma_dia", "petroleo_var_28", "transacciones_28"]
        + COLUMNAS_CALENDARIO
    )


def _a_largo(ancho: pd.DataFrame, nombre: str) -> pd.Series:
    """Convierte una tabla fechas × series a una columna con índice (store, family, date)."""
    largo = ancho.T.stack(future_stack=True)
    largo.index = largo.index.set_names(["store_nbr", "family", "date"])
    return largo.rename(nombre)


def _banderas_feriados(
    feriados: pd.DataFrame, tiendas: pd.DataFrame, fechas: pd.DatetimeIndex
) -> pd.DataFrame:
    """Banderas de calendario por (tienda, fecha) a partir del catálogo de feriados."""
    f = feriados.copy()
    f["date"] = pd.to_datetime(f["date"])
    f["transferred"] = f["transferred"].astype(str).str.lower().isin(["true", "1"])
    libres = f[f["type"].isin(TIPOS_FERIADO) & ~f["transferred"]]
    nacional = set(libres.loc[libres["locale"] == "National", "date"])
    regional = set(zip(libres.loc[libres["locale"] == "Regional", "date"],
                       libres.loc[libres["locale"] == "Regional", "locale_name"], strict=True))
    local = set(zip(libres.loc[libres["locale"] == "Local", "date"],
                    libres.loc[libres["locale"] == "Local", "locale_name"], strict=True))
    eventos = set(f.loc[(f["type"] == "Event") & (f["locale"] == "National"), "date"])
    laborales = set(f.loc[f["type"] == "Work Day", "date"])

    filas = pd.MultiIndex.from_product(
        [tiendas["store_nbr"].astype(int), fechas], names=["store_nbr", "date"]
    ).to_frame(index=False)
    info = tiendas.set_index("store_nbr")
    filas["state"] = filas["store_nbr"].map(info["state"])
    filas["city"] = filas["store_nbr"].map(info["city"])
    filas["feriado_nacional"] = filas["date"].isin(nacional)
    filas["feriado_regional"] = [
        (d, s) in regional for d, s in zip(filas["date"], filas["state"], strict=True)
    ]
    filas["feriado_local"] = [
        (d, c) in local for d, c in zip(filas["date"], filas["city"], strict=True)
    ]
    filas["evento_nacional"] = filas["date"].isin(eventos)
    filas["dia_laboral"] = filas["date"].isin(laborales)
    columnas = ["feriado_nacional", "feriado_regional", "feriado_local", "evento_nacional",
                "dia_laboral"]
    filas[columnas] = filas[columnas].astype("int8")
    return filas[["store_nbr", "date", *columnas]]


def construir_dataset(
    fuentes: Fuentes,
    horizonte: int,
    params: ParametrosModelo,
) -> pd.DataFrame:
    """Filas de entrenamiento, validación y horizonte para el corte de ``fuentes``.

    Devuelve una fila por (tienda, familia, fecha) desde el inicio de la ventana de entrenamiento
    hasta ``corte + horizonte``. ``sales`` es nulo en el horizonte (``es_futuro = 1``).
    """
    corte = fuentes.corte
    if min(params.lags) < horizonte:
        raise ValueError("Todos los rezagos deben ser >= horizonte")
    primera_fila = corte - pd.Timedelta(days=params.ventana_entrenamiento + params.dias_validacion
                                        - 1)
    colchon = horizonte + max(max(params.lags), max(params.ventanas),
                              7 * (params.semanas_baseline + 3), 28) + 7
    inicio = primera_fila - pd.Timedelta(days=colchon)
    fechas = pd.date_range(inicio, corte + pd.Timedelta(days=horizonte), freq="D")

    # Ventas conocidas al corte (por construcción, nada posterior).
    ventas = fuentes.ventas[(fuentes.ventas["date"] >= inicio) & (fuentes.ventas["date"] <= corte)]
    tiendas = sorted(fuentes.tiendas["store_nbr"].astype(int))
    columnas_series = pd.MultiIndex.from_product([tiendas, fuentes.familias],
                                                 names=["store_nbr", "family"])
    ancho = (
        ventas.pivot_table(index="date", columns=["store_nbr", "family"], values="sales",
                           aggfunc="last")
        .reindex(index=fechas, columns=columnas_series)
        .astype("float64")
    )
    ancho.index.name = "date"

    variables: dict[str, pd.DataFrame] = {"sales": ancho}
    for k in params.lags:
        variables[f"lag_{k}"] = ancho.shift(k)
    base = ancho.shift(horizonte)
    for w in params.ventanas:
        variables[f"media_{w}"] = base.rolling(w, min_periods=1).mean()
    variables["proporcion_ceros_28"] = (base == 0).astype("float64").where(base.notna()).rolling(
        28, min_periods=1).mean()
    # Baseline: promedio de las últimas N semanas del mismo día de la semana con datos hasta
    # t - horizonte (rezagos múltiplos de 7 a partir del primero >= horizonte).
    primera_semana = -(-horizonte // 7)
    semanas = range(primera_semana, primera_semana + params.semanas_baseline)
    rezagos_semana = [7 * j for j in semanas]
    apilado = np.stack([ancho.shift(r).to_numpy() for r in rezagos_semana])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)  # series sin datos: NaN
        baseline = np.nanmean(apilado, axis=0)
    variables["baseline_misma_dia"] = pd.DataFrame(baseline, index=ancho.index,
                                                   columns=ancho.columns)

    largo = pd.concat([_a_largo(v, n) for n, v in variables.items()], axis=1).reset_index()

    # Petróleo: variación de 28 días del último precio conocido en t - horizonte. Se usa la
    # variación y no el nivel, porque el nivel funciona como un reloj (ver DECISIONES.md, D5).
    precios = fuentes.oil[fuentes.oil["date"] <= corte].set_index("date")["dcoilwtico"].dropna()
    calendario = pd.date_range(min([inicio, *precios.index[:1]]), fechas[-1], freq="D")
    oil = precios.reindex(calendario).ffill().shift(horizonte)
    largo["petroleo_var_28"] = largo["date"].map((oil / oil.shift(28) - 1).reindex(fechas))

    # Tienda cerrada: ese día la tienda no vendió nada en ninguna familia (por ejemplo, el 1 de
    # enero). No es demanda cero, así que esas filas no se usan para entrenar ni para evaluar.
    total_tienda = ancho.T.groupby(level="store_nbr").sum(min_count=1).T
    cerrada = (total_tienda == 0).stack(future_stack=True).rename("tienda_cerrada")
    cerrada.index = cerrada.index.set_names(["date", "store_nbr"])
    largo = largo.merge(cerrada.astype("int8").reset_index(), on=["date", "store_nbr"],
                        how="left")
    largo["tienda_cerrada"] = largo["tienda_cerrada"].fillna(0).astype("int8")

    # Transacciones de la tienda: media de 28 días hasta t - horizonte.
    trans = (
        fuentes.transactions[fuentes.transactions["date"] <= corte]
        .pivot_table(index="date", columns="store_nbr", values="transactions", aggfunc="last")
        .reindex(index=fechas, columns=tiendas)
        .shift(horizonte)
        .rolling(28, min_periods=1)
        .mean()
    )
    trans_largo = trans.stack(future_stack=True).rename("transacciones_28")
    trans_largo.index = trans_largo.index.set_names(["date", "store_nbr"])
    largo = largo.merge(trans_largo.reset_index(), on=["date", "store_nbr"], how="left")

    # Calendario de la fecha objetivo.
    fecha = largo["date"]
    largo["dia_semana"] = fecha.dt.dayofweek
    largo["dia_mes"] = fecha.dt.day
    largo["mes"] = fecha.dt.month
    largo["semana_anio"] = fecha.dt.isocalendar().week.astype("int64").to_numpy()
    largo["es_fin_semana"] = (largo["dia_semana"] >= 5).astype("int8")
    # En Ecuador el sector público paga los días 15 y el último día del mes.
    largo["dia_pago"] = ((fecha.dt.day == 15) | fecha.dt.is_month_end).astype("int8")
    largo = largo.merge(_banderas_feriados(fuentes.feriados, fuentes.tiendas, fechas),
                        on=["store_nbr", "date"], how="left")

    info = fuentes.tiendas.set_index("store_nbr")
    largo["cluster"] = largo["store_nbr"].map(info["cluster"]).astype("int64")
    largo["tipo_tienda"] = (
        largo["store_nbr"].map(info["type"]).map(TIPOS_TIENDA).fillna(5).astype("int64")
    )
    codigos = {f: i for i, f in enumerate(fuentes.familias)}
    largo["familia_cod"] = largo["family"].map(codigos).astype("int64")

    largo = largo[largo["date"] >= primera_fila].copy()
    largo["es_futuro"] = (largo["date"] > corte).astype("int8")
    largo["corte"] = corte
    flotantes = [c for c in largo.columns if c.startswith(("lag_", "media_"))] + [
        "proporcion_ceros_28", "baseline_misma_dia", "petroleo_var_28", "transacciones_28"]
    largo[flotantes] = largo[flotantes].astype("float32")
    orden = ["date", "store_nbr", "family", "sales", "es_futuro", "corte", "tienda_cerrada"]
    resto = [c for c in largo.columns if c not in orden]
    return largo[orden + resto].sort_values(["date", "store_nbr", "family"]).reset_index(drop=True)
