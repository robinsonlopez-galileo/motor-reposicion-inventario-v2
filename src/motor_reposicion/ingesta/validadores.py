"""Validación de los archivos que llegan a la bandeja.

Hay dos niveles (DECISIONES.md, D7):

- Estructura: si el archivo no se puede leer, está vacío o le faltan columnas, no se puede procesar.
  La tarea falla y el día queda sin marcar como ingerido, para que alguien lo revise.
- Filas: las filas con valores imposibles (fecha inválida, tienda o familia desconocida, ventas
  negativas o no numéricas) se descartan y se guardan con su motivo en ``control/rechazos/``. El
  resto del archivo se consolida.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

COLUMNAS_REQUERIDAS: dict[str, list[str]] = {
    "ventas": ["date", "store_nbr", "family", "sales", "onpromotion"],
    "oil": ["date", "dcoilwtico"],
    "transactions": ["date", "store_nbr", "transactions"],
    "stores": ["store_nbr", "city", "state", "type", "cluster"],
    "holidays_events": ["date", "type", "locale", "locale_name", "description", "transferred"],
}


class ErrorEstructura(ValueError):
    """El archivo no se puede procesar (ilegible, vacío o sin las columnas esperadas)."""


@dataclass
class ResultadoValidacion:
    fuente: str
    filas_leidas: int
    validas: pd.DataFrame
    rechazadas: pd.DataFrame
    duplicadas: int = 0
    avisos: list[str] = field(default_factory=list)

    def resumen(self) -> dict:
        motivos = (
            self.rechazadas["motivo"].value_counts().to_dict() if len(self.rechazadas) else {}
        )
        return {
            "fuente": self.fuente,
            "filas_leidas": self.filas_leidas,
            "filas_validas": len(self.validas),
            "filas_rechazadas": len(self.rechazadas),
            "duplicadas": self.duplicadas,
            "motivos_rechazo": {str(k): int(v) for k, v in motivos.items()},
            "avisos": list(self.avisos),
        }


def validar_estructura(df: pd.DataFrame, fuente: str) -> list[str]:
    """Errores de estructura: columnas faltantes o archivo vacío."""
    errores: list[str] = []
    if fuente not in COLUMNAS_REQUERIDAS:
        return [f"Fuente desconocida: {fuente}"]
    faltantes = [c for c in COLUMNAS_REQUERIDAS[fuente] if c not in df.columns]
    if faltantes:
        errores.append(f"Columnas faltantes en '{fuente}': {faltantes}")
    if df.empty:
        errores.append(f"El archivo de '{fuente}' no tiene filas")
    return errores


def _numerico(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce")


def validar_filas(
    df: pd.DataFrame,
    fuente: str,
    tiendas: set[int],
    familias: set[str] | None = None,
) -> ResultadoValidacion:
    """Separa filas válidas y rechazadas. Supone que la estructura ya se validó."""
    errores = validar_estructura(df, fuente)
    if errores:
        raise ErrorEstructura("; ".join(errores))

    datos = df.copy()
    motivo = pd.Series("", index=datos.index, dtype=object)

    def marcar(condicion: pd.Series, texto: str) -> None:
        nuevos = condicion & (motivo == "")
        motivo[nuevos] = texto

    fechas = pd.to_datetime(datos["date"].astype(str).str.strip(), format="%Y-%m-%d",
                            errors="coerce")
    marcar(fechas.isna(), "fecha inválida")
    datos["date"] = fechas

    if "store_nbr" in COLUMNAS_REQUERIDAS[fuente]:
        tienda = _numerico(datos["store_nbr"])
        es_entero = tienda.notna() & np.isclose(tienda.fillna(-1) % 1, 0)
        marcar(~es_entero, "tienda no numérica")
        marcar(es_entero & ~tienda.isin(list(tiendas)), "tienda desconocida")
        datos["store_nbr"] = tienda

    if fuente == "ventas":
        familia = datos["family"].astype(str).str.strip().str.upper()
        if familias is not None:
            marcar(~familia.isin(list(familias)), "familia desconocida")
        datos["family"] = familia
        ventas = _numerico(datos["sales"])
        marcar(ventas.isna(), "venta no numérica")
        marcar(ventas < 0, "venta negativa")
        datos["sales"] = ventas
        promo = _numerico(datos["onpromotion"])
        marcar(promo.isna() | (promo < 0), "promoción inválida")
        datos["onpromotion"] = promo
    elif fuente == "oil":
        # El precio puede faltar (feriados de la bolsa): se conserva como nulo.
        datos["dcoilwtico"] = _numerico(datos["dcoilwtico"])
    elif fuente == "transactions":
        transacciones = _numerico(datos["transactions"])
        marcar(transacciones.isna() | (transacciones < 0), "transacciones inválidas")
        datos["transactions"] = transacciones

    rechazadas = df[motivo != ""].copy()
    rechazadas["motivo"] = motivo[motivo != ""]
    validas = datos[motivo == ""].copy()
    for col in ("store_nbr", "onpromotion", "transactions"):
        if col in validas.columns:
            validas[col] = validas[col].round().astype("int64")

    claves = [c for c in ("date", "store_nbr", "family") if c in validas.columns]
    duplicadas = int(validas.duplicated(claves, keep="last").sum())
    validas = validas.drop_duplicates(claves, keep="last")

    avisos = []
    if duplicadas:
        avisos.append(f"{duplicadas} filas repetidas en el archivo: se conservó la última")
    return ResultadoValidacion(fuente, len(df), validas.reset_index(drop=True),
                               rechazadas.reset_index(drop=True), duplicadas, avisos)
