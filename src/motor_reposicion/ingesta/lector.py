"""Lectura de la bandeja (``data/inbox/``).

Convención: ``inbox/<fuente>/<fuente>_<AAAA-MM-DD>[_sufijo].csv``. La fecha del nombre es el día
en que el sistema de origen entregó el archivo. Un archivo con sufijo (por ejemplo
``ventas_2017-03-10_correccion.csv``) es una entrega adicional del mismo día y se procesa después
del archivo principal; sus filas pueden traer fechas anteriores (correcciones).
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

_PATRON = re.compile(r"^(?P<fuente>[a-z_]+)_(?P<fecha>\d{4}-\d{2}-\d{2})(?P<sufijo>_.+)?\.csv$")


def archivos_del_dia(inbox: Path, fuente: str, fecha: pd.Timestamp | str) -> list[Path]:
    """Archivos de la fuente entregados ese día, en orden de procesamiento."""
    fecha_txt = f"{pd.Timestamp(fecha):%Y-%m-%d}"
    carpeta = inbox / fuente
    if not carpeta.exists():
        return []
    encontrados = []
    for ruta in carpeta.glob(f"{fuente}_{fecha_txt}*.csv"):
        m = _PATRON.match(ruta.name)
        if m and m["fuente"] == fuente and m["fecha"] == fecha_txt:
            encontrados.append(ruta)
    # Primero el archivo principal (sin sufijo) y luego las entregas adicionales por nombre.
    return sorted(encontrados, key=lambda r: (_PATRON.match(r.name)["sufijo"] is not None, r.name))


def leer_csv(ruta: Path) -> pd.DataFrame:
    """Lee un CSV de la bandeja como texto; la validación decide cómo interpretar cada valor."""
    return pd.read_csv(ruta, dtype=str, keep_default_na=False, na_values=[""])


def leer_entrega(inbox: Path, fuente: str, fecha: pd.Timestamp | str) -> pd.DataFrame | None:
    """Une todos los archivos del día de una fuente, o ``None`` si no llegó ninguno."""
    archivos = archivos_del_dia(inbox, fuente, fecha)
    if not archivos:
        return None
    return pd.concat([leer_csv(r) for r in archivos], ignore_index=True)
