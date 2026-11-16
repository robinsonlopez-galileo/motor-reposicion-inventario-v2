"""Escritura atómica de archivos: primero a un temporal en la misma carpeta y luego se renombra.

Así, una tarea interrumpida nunca deja un archivo a medias que otra tarea pueda leer.
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pandas as pd


def _temporal(ruta: Path) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    return ruta.with_name(f".{ruta.name}.{uuid.uuid4().hex}.tmp")


def escribir_parquet(df: pd.DataFrame, ruta: Path) -> Path:
    temporal = _temporal(ruta)
    df.to_parquet(temporal, index=False)
    os.replace(temporal, ruta)
    return ruta


def escribir_csv(df: pd.DataFrame, ruta: Path) -> Path:
    temporal = _temporal(ruta)
    df.to_csv(temporal, index=False)
    os.replace(temporal, ruta)
    return ruta


def escribir_json(datos: dict, ruta: Path) -> Path:
    temporal = _temporal(ruta)
    temporal.write_text(json.dumps(datos, indent=2, ensure_ascii=False, default=str),
                        encoding="utf-8")
    os.replace(temporal, ruta)
    return ruta
