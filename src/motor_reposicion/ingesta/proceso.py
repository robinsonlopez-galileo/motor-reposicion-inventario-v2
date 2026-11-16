"""Ingesta diaria: validar la entrega de la bandeja, consolidarla y marcar el día como ingerido.

Los tres pasos son idempotentes y solo escriben archivos propios del día procesado, de modo que el
DAG puede reintentar o procesar varios días en paralelo sin pisarse.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from motor_reposicion.archivos import escribir_csv, escribir_json, escribir_parquet
from motor_reposicion.configuracion import Rutas
from motor_reposicion.ingesta import almacen
from motor_reposicion.ingesta.lector import leer_entrega
from motor_reposicion.ingesta.validadores import (
    ErrorEstructura,
    validar_estructura,
    validar_filas,
)


def _fecha(fecha: pd.Timestamp | str) -> pd.Timestamp:
    return pd.Timestamp(fecha).normalize()


def _ruta_validadas(rutas: Rutas, fuente: str, fecha: pd.Timestamp) -> Path:
    return rutas.control / "validadas" / fuente / f"{fecha:%Y-%m-%d}.parquet"


def validar_entrega(rutas: Rutas, fuente: str, fecha: pd.Timestamp | str) -> dict:
    """Valida los archivos del día y deja las filas válidas listas para consolidar.

    Lanza ``ErrorEstructura`` si el archivo no se puede procesar.
    """
    fecha = _fecha(fecha)
    staging = _ruta_validadas(rutas, fuente, fecha)
    rechazos = rutas.control / "rechazos" / f"{fuente}_{fecha:%Y-%m-%d}.csv"
    df = leer_entrega(rutas.inbox, fuente, fecha)
    if df is None:
        for viejo in (staging, rechazos):
            viejo.unlink(missing_ok=True)
        return {"fuente": fuente, "fecha": f"{fecha:%Y-%m-%d}", "estado": "sin_archivo"}

    errores = validar_estructura(df, fuente)
    if errores:
        raise ErrorEstructura(f"{fuente} {fecha:%Y-%m-%d}: " + "; ".join(errores))

    tiendas = set(almacen.leer_catalogo(rutas.raw, "stores")["store_nbr"].astype(int))
    familias = None
    if fuente == "ventas":
        familias = set(almacen.leer_catalogo(rutas.raw, "familias")["family"].astype(str))
    resultado = validar_filas(df, fuente, tiendas, familias)

    escribir_parquet(almacen.normalizar(resultado.validas, fuente), staging)
    if len(resultado.rechazadas):
        escribir_csv(resultado.rechazadas, rechazos)
    else:
        rechazos.unlink(missing_ok=True)
    return {"fecha": f"{fecha:%Y-%m-%d}", "estado": "validado", **resultado.resumen()}


def consolidar_entrega(rutas: Rutas, fuente: str, fecha: pd.Timestamp | str) -> dict:
    """Incorpora al histórico consolidado las filas validadas del día."""
    fecha = _fecha(fecha)
    staging = _ruta_validadas(rutas, fuente, fecha)
    if not staging.exists():
        # Sin entrega ese día: se eliminan restos de una ejecución anterior (idempotencia).
        almacen.escribir_entrega(rutas.raw, fuente, fecha,
                                 pd.DataFrame(columns=almacen.COLUMNAS[fuente]))
        return {"fuente": fuente, "fecha": f"{fecha:%Y-%m-%d}", "estado": "sin_archivo"}
    validas = pd.read_parquet(staging)
    resumen = almacen.escribir_entrega(rutas.raw, fuente, fecha, validas)
    return {"fuente": fuente, "fecha": f"{fecha:%Y-%m-%d}", "estado": "consolidado", **resumen}


def ruta_marcador(rutas: Rutas, fecha: pd.Timestamp | str) -> Path:
    return rutas.control / "ingesta" / f"{_fecha(fecha):%Y-%m-%d}.json"


def registrar_ingesta(rutas: Rutas, fecha: pd.Timestamp | str, resultados: list[dict]) -> dict:
    """Marca el día como ingerido. Los pasos posteriores esperan este marcador."""
    fecha = _fecha(fecha)
    marcador = {"fecha": f"{fecha:%Y-%m-%d}", "fuentes": resultados}
    escribir_json(marcador, ruta_marcador(rutas, fecha))
    return marcador


def dias_sin_ingerir(rutas: Rutas, desde: pd.Timestamp, hasta: pd.Timestamp) -> list[str]:
    """Días del rango que todavía no tienen marcador de ingesta."""
    faltantes = []
    for dia in pd.date_range(_fecha(desde), _fecha(hasta), freq="D"):
        if not ruta_marcador(rutas, dia).exists():
            faltantes.append(f"{dia:%Y-%m-%d}")
    return faltantes


def ingerir_dia(rutas: Rutas, fuentes: tuple[str, ...], fecha: pd.Timestamp | str) -> dict:
    """Ingesta completa de un día (lo que hace el DAG, en un solo llamado)."""
    resultados = []
    for fuente in fuentes:
        validacion = validar_entrega(rutas, fuente, fecha)
        consolidacion = consolidar_entrega(rutas, fuente, fecha)
        resultados.append({**validacion, **consolidacion})
    return registrar_ingesta(rutas, fecha, resultados)


__all__ = [
    "ErrorEstructura",
    "consolidar_entrega",
    "dias_sin_ingerir",
    "ingerir_dia",
    "registrar_ingesta",
    "ruta_marcador",
    "validar_entrega",
]
