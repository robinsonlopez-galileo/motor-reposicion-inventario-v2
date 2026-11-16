"""Registro de modelos en ``data/models/``.

- ``candidatos/<tipo>_<corte>.pkl``: candidato de boosting y baseline de cada semana.
- ``evaluaciones/<corte>.json``: métricas de candidato, baseline y vigente en la validación.
- ``decisiones/<corte>.json``: decisión de la compuerta y modelo vigente que resulta.

El vigente para un corte es el que dejó la última decisión anterior a ese corte. Por eso, volver a
ejecutar una semana produce exactamente el mismo resultado (idempotencia) y no depende del orden en
que se ejecutaron las demás.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import pandas as pd

from motor_reposicion.archivos import escribir_json


def _txt(corte: pd.Timestamp | str) -> str:
    return f"{pd.Timestamp(corte):%Y-%m-%d}"


def ruta_candidato(models: Path, corte, tipo: str) -> Path:
    return models / "candidatos" / f"{tipo}_{_txt(corte)}.pkl"


def guardar_modelo(modelo, ruta: Path) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(".tmp")
    with open(temporal, "wb") as f:
        pickle.dump(modelo, f, protocol=5)
    temporal.replace(ruta)
    return ruta


def cargar_modelo(ruta: Path):
    with open(ruta, "rb") as f:
        return pickle.load(f)


def guardar_evaluacion(models: Path, corte, datos: dict) -> Path:
    ruta = models / "evaluaciones" / f"{_txt(corte)}.json"
    escribir_json(datos, ruta)
    return ruta


def leer_evaluacion(models: Path, corte) -> dict:
    return json.loads((models / "evaluaciones" / f"{_txt(corte)}.json").read_text("utf-8"))


def guardar_decision(models: Path, corte, datos: dict) -> Path:
    ruta = models / "decisiones" / f"{_txt(corte)}.json"
    escribir_json(datos, ruta)
    return ruta


def leer_decision(models: Path, corte) -> dict | None:
    ruta = models / "decisiones" / f"{_txt(corte)}.json"
    return json.loads(ruta.read_text("utf-8")) if ruta.exists() else None


def vigente_antes_de(models: Path, corte) -> dict | None:
    """Modelo vigente al empezar la semana ``corte`` (o ``None`` si todavía no hay ninguno)."""
    corte = pd.Timestamp(corte)
    anteriores = sorted(
        r for r in (models / "decisiones").glob("*.json") if pd.Timestamp(r.stem) < corte
    )
    if not anteriores:
        return None
    return json.loads(anteriores[-1].read_text("utf-8"))["vigente"]


def historial_decisiones(models: Path) -> pd.DataFrame:
    filas = []
    for ruta in sorted((models / "decisiones").glob("*.json")):
        d = json.loads(ruta.read_text("utf-8"))
        filas.append({
            "corte": d["corte"],
            "accion": d["decision"]["accion"],
            "motivo": d["decision"]["motivo"],
            "vigente": d["vigente"]["modelo"],
            "vigente_desde": d["vigente"]["desde"],
        })
    return pd.DataFrame(filas)
