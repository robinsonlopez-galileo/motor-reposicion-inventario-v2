"""Almacenamiento de las fuentes consolidadas en ``data/raw/``.

Cada fuente diaria se guarda en tres partes, para que la ingesta de un día nunca escriba un archivo
que otra ejecución también escribe (los DAGs pueden procesar varios días a la vez):

- ``raw/<fuente>/historico.parquet``: carga histórica inicial (hasta el corte).
- ``raw/<fuente>/dias/<AAAA-MM-DD>.parquet``: filas de la entrega de ese día cuya fecha es ese día.
- ``raw/<fuente>/correcciones/<AAAA-MM-DD>.parquet``: filas de la entrega de ese día que corrigen
  fechas anteriores.

Al leer, las partes se concatenan en ese orden y, ante claves repetidas, gana la última: una
corrección siempre reemplaza al dato original (DECISIONES.md, D6).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from motor_reposicion.archivos import escribir_parquet

COLUMNAS: dict[str, list[str]] = {
    "ventas": ["date", "store_nbr", "family", "sales", "onpromotion"],
    "oil": ["date", "dcoilwtico"],
    "transactions": ["date", "store_nbr", "transactions"],
    "stores": ["store_nbr", "city", "state", "type", "cluster"],
    "holidays_events": ["date", "type", "locale", "locale_name", "description", "transferred"],
    "familias": ["family"],
}

CLAVES: dict[str, list[str]] = {
    "ventas": ["date", "store_nbr", "family"],
    "oil": ["date"],
    "transactions": ["date", "store_nbr"],
}

_TIPOS: dict[str, str] = {
    "store_nbr": "int64",
    "sales": "float64",
    "onpromotion": "int64",
    "dcoilwtico": "float64",
    "transactions": "int64",
    "cluster": "int64",
}


def normalizar(df: pd.DataFrame, fuente: str) -> pd.DataFrame:
    """Deja el DataFrame con las columnas y tipos de almacenamiento de la fuente."""
    columnas = COLUMNAS[fuente]
    salida = df.loc[:, columnas].copy()
    for col in columnas:
        if col == "date":
            salida[col] = pd.to_datetime(salida[col]).dt.normalize().astype("datetime64[ns]")
        elif col == "transferred":
            salida[col] = salida[col].astype(str).str.lower().isin(["true", "1"])
        elif col in _TIPOS:
            salida[col] = salida[col].astype(_TIPOS[col])
        else:
            salida[col] = salida[col].astype(str)
    return salida.reset_index(drop=True)


def carpeta_fuente(raw: Path, fuente: str) -> Path:
    return raw / fuente


def escribir_historico(raw: Path, fuente: str, df: pd.DataFrame) -> Path:
    ruta = carpeta_fuente(raw, fuente) / "historico.parquet"
    escribir_parquet(normalizar(df, fuente), ruta)
    return ruta


def escribir_entrega(raw: Path, fuente: str, fecha: pd.Timestamp, df: pd.DataFrame) -> dict:
    """Guarda las filas validadas de la entrega del día ``fecha``.

    Es idempotente: volver a ejecutarla con la misma entrega deja los mismos archivos.
    """
    fecha = pd.Timestamp(fecha).normalize()
    datos = normalizar(df, fuente)
    datos = datos.drop_duplicates(CLAVES[fuente], keep="last")
    nombre = f"{fecha:%Y-%m-%d}.parquet"
    del_dia = datos[datos["date"] == fecha]
    correcciones = datos[datos["date"] != fecha]
    resumen = {"filas_del_dia": len(del_dia), "filas_correccion": len(correcciones)}
    for subcarpeta, parte in (("dias", del_dia), ("correcciones", correcciones)):
        ruta = carpeta_fuente(raw, fuente) / subcarpeta / nombre
        if len(parte):
            escribir_parquet(parte.sort_values(CLAVES[fuente]).reset_index(drop=True), ruta)
        elif ruta.exists():
            ruta.unlink()
    return resumen


def _fecha_archivo(ruta: Path) -> pd.Timestamp:
    return pd.Timestamp(ruta.stem)


def leer_fuente(
    raw: Path,
    fuente: str,
    hasta: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Lee la fuente consolidada.

    Con ``hasta`` solo se usan las entregas recibidas hasta ese día y las filas con fecha hasta ese
    día: es exactamente lo que se conocía al cierre de ``hasta`` (sin información futura).
    """
    carpeta = carpeta_fuente(raw, fuente)
    historico = carpeta / "historico.parquet"
    if not historico.exists():
        raise FileNotFoundError(f"No existe la carga histórica de '{fuente}' en {historico}")
    partes = [historico]
    for subcarpeta in ("dias", "correcciones"):
        archivos = sorted((carpeta / subcarpeta).glob("*.parquet"))
        if hasta is not None:
            archivos = [a for a in archivos if _fecha_archivo(a) <= hasta]
        partes.extend(archivos)
    df = pd.concat([pd.read_parquet(p) for p in partes], ignore_index=True)
    df = df.drop_duplicates(CLAVES[fuente], keep="last")
    if hasta is not None:
        df = df[df["date"] <= pd.Timestamp(hasta)]
    return df.sort_values(CLAVES[fuente]).reset_index(drop=True)


def escribir_catalogo(raw: Path, nombre: str, df: pd.DataFrame) -> Path:
    ruta = raw / "catalogos" / f"{nombre}.parquet"
    escribir_parquet(normalizar(df, nombre), ruta)
    return ruta


def leer_catalogo(raw: Path, nombre: str) -> pd.DataFrame:
    ruta = raw / "catalogos" / f"{nombre}.parquet"
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el catálogo '{nombre}' en {ruta}")
    return pd.read_parquet(ruta)
