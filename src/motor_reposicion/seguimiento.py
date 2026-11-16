"""Seguimiento del desempeño: pronósticos publicados frente a las ventas reales.

Cada semana (el lunes del corte) se evalúan los 7 días que terminan ese lunes contra todos los
pronósticos publicados que los cubrían. Para cada pronóstico y día se calcula el error técnico de
la venta esperada y el costo real que habría tenido el pedido sugerido (merma y quiebre), y lo
mismo para el baseline publicado junto al pronóstico, como referencia.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from motor_reposicion.archivos import escribir_csv, escribir_json, escribir_parquet
from motor_reposicion.configuracion import Costos, Rutas
from motor_reposicion.ingesta import almacen
from motor_reposicion.modelo.metricas import metricas_tecnicas
from motor_reposicion.pedido import costo_pedido


def ruta_pronostico(rutas: Rutas, corte) -> Path:
    return rutas.forecasts / f"pronostico_{pd.Timestamp(corte):%Y-%m-%d}.parquet"


def pronosticos_que_cubren(rutas: Rutas, desde: pd.Timestamp, hasta: pd.Timestamp,
                           horizonte: int) -> list[Path]:
    """Archivos de pronóstico cuyo horizonte toca el rango [desde, hasta]."""
    archivos = []
    for ruta in sorted(rutas.forecasts.glob("pronostico_*.parquet")):
        corte = pd.Timestamp(ruta.stem.removeprefix("pronostico_"))
        if corte < hasta and corte + pd.Timedelta(days=horizonte) >= desde:
            archivos.append(ruta)
    return archivos


def evaluar_semana(rutas: Rutas, fecha, costos: Costos) -> pd.DataFrame:
    """Compara los 7 días que terminan en ``fecha`` con los pronósticos que los cubrían."""
    fecha = pd.Timestamp(fecha).normalize()
    desde = fecha - pd.Timedelta(days=6)
    reales = almacen.leer_fuente(rutas.raw, "ventas", hasta=fecha)
    reales = reales[reales["date"] >= desde][["date", "store_nbr", "family", "sales"]]
    filas = []
    for ruta in pronosticos_que_cubren(rutas, desde, fecha, costos.horizonte):
        pron = pd.read_parquet(ruta)
        cruce = pron.merge(reales, on=["date", "store_nbr", "family"], how="inner")
        for dia, grupo in cruce.groupby("date"):
            real = grupo["sales"].to_numpy()
            modelo = metricas_tecnicas(real, grupo["venta_esperada"].to_numpy())
            fila = {
                "semana": f"{fecha:%Y-%m-%d}",
                "corte": f"{pd.Timestamp(grupo['corte'].iloc[0]):%Y-%m-%d}",
                "date": f"{dia:%Y-%m-%d}",
                "horizonte_dia": int((dia - pd.Timestamp(grupo["corte"].iloc[0])).days),
                "modelo": str(grupo["modelo"].iloc[0]),
                "n": modelo["n"],
                "venta_real": round(float(real.sum()), 1),
                "MAE": modelo["MAE"],
                "RMSE": modelo["RMSE"],
                "WAPE": modelo["WAPE"],
                **costo_pedido(real, grupo["pedido_sugerido"].to_numpy(), costos),
            }
            base = costo_pedido(real, grupo["pedido_baseline"].to_numpy(), costos)
            fila["WAPE_baseline"] = metricas_tecnicas(real, grupo["venta_baseline"].to_numpy())[
                "WAPE"]
            fila["costo_total_baseline"] = base["costo_total"]
            filas.append(fila)
    resultado = pd.DataFrame(filas)
    escribir_parquet(resultado, rutas.reports / "seguimiento" / f"{fecha:%Y-%m-%d}.parquet")
    return resultado


def consolidar(rutas: Rutas) -> dict:
    """Regenera los reportes acumulados a partir de los archivos semanales (idempotente)."""
    archivos = sorted((rutas.reports / "seguimiento").glob("*.parquet"))
    partes = [pd.read_parquet(a) for a in archivos]
    partes = [p for p in partes if len(p)]
    if not partes:
        return {"pronosticos_evaluados": 0}
    detalle = pd.concat(partes, ignore_index=True)
    # Un mismo (corte, día) puede aparecer una sola vez: cada día cae en una única semana.
    detalle = detalle.drop_duplicates(["corte", "date"], keep="last").sort_values(
        ["corte", "date"])
    escribir_csv(detalle, rutas.reports / "historial_desempeno.csv")

    resumen = detalle.groupby("corte").agg(
        modelo=("modelo", "first"),
        dias_evaluados=("date", "nunique"),
        venta_real=("venta_real", "sum"),
        costo_total=("costo_total", "sum"),
        costo_merma=("costo_merma", "sum"),
        costo_quiebre=("costo_quiebre", "sum"),
        costo_total_baseline=("costo_total_baseline", "sum"),
        error_abs=("MAE", lambda s: float((s * detalle.loc[s.index, "n"]).sum())),
    ).reset_index()
    resumen["WAPE"] = (resumen.pop("error_abs") / resumen["venta_real"]).round(4)
    resumen["ahorro_vs_baseline_pct"] = (
        (resumen["costo_total_baseline"] - resumen["costo_total"])
        / resumen["costo_total_baseline"] * 100
    ).round(2)
    escribir_csv(resumen, rutas.reports / "resumen_por_pronostico.csv")

    general = {
        "pronosticos_evaluados": int(len(resumen)),
        "dias_pronostico_evaluados": int(len(detalle)),
        "costo_total_motor": round(float(detalle["costo_total"].sum()), 2),
        "costo_total_baseline": round(float(detalle["costo_total_baseline"].sum()), 2),
    }
    if general["costo_total_baseline"] > 0:
        general["ahorro_vs_baseline_pct"] = round(
            (general["costo_total_baseline"] - general["costo_total_motor"])
            / general["costo_total_baseline"] * 100, 2)
    escribir_json(general, rutas.reports / "resumen_general.json")
    return general
