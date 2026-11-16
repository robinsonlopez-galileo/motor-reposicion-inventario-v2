"""Construcción de la carga histórica inicial y de la bandeja a partir de los archivos de Kaggle.

Entrada: los CSV de la competencia *Store Sales - Time Series Forecasting* en ``datos/kaggle/``
(sueltos o dentro del ZIP que descarga Kaggle). Salida:

- ``data/raw/<fuente>/historico.parquet`` con las filas hasta ``corte_historico``.
- ``data/raw/catalogos/`` con tiendas, feriados (calendario completo) y familias.
- ``data/inbox/<fuente>/<fuente>_<AAAA-MM-DD>.csv``: un archivo por día después del corte, hasta
  ``fin_operacion``, que simula lo que el sistema de origen entrega cada día.

Es idempotente: si ya se construyó con los mismos archivos y el mismo periodo, no hace nada.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from motor_reposicion.configuracion import Operacion, Rutas
from motor_reposicion.ingesta import almacen
from motor_reposicion.ingesta.validadores import validar_estructura

logger = logging.getLogger(__name__)

ARCHIVOS_KAGGLE = {
    "train": "train.csv",
    "stores": "stores.csv",
    "oil": "oil.csv",
    "holidays_events": "holidays_events.csv",
    "transactions": "transactions.csv",
}
FUENTE_DE_ARCHIVO = {"train": "ventas", "oil": "oil", "transactions": "transactions"}


class ErrorCargaInicial(RuntimeError):
    """Faltan archivos de Kaggle o la carga existente no coincide con la configuración."""


@dataclass(frozen=True)
class ArchivoKaggle:
    ruta: Path
    miembro: str | None = None  # nombre dentro del ZIP, si viene comprimido

    def leer(self, **kwargs) -> pd.DataFrame:
        if self.miembro is None:
            return pd.read_csv(self.ruta, **kwargs)
        with zipfile.ZipFile(self.ruta) as z, z.open(self.miembro) as f:
            return pd.read_csv(f, **kwargs)


def localizar_archivos(kaggle: Path) -> dict[str, ArchivoKaggle]:
    """Busca los CSV de Kaggle sueltos o dentro de un ZIP en la carpeta indicada."""
    encontrados: dict[str, ArchivoKaggle] = {}
    if kaggle.exists():
        for clave, nombre in ARCHIVOS_KAGGLE.items():
            directo = kaggle / nombre
            if directo.exists():
                encontrados[clave] = ArchivoKaggle(directo)
        for zip_path in sorted(kaggle.glob("*.zip")):
            with zipfile.ZipFile(zip_path) as z:
                miembros = {Path(m).name: m for m in z.namelist()}
            for clave, nombre in ARCHIVOS_KAGGLE.items():
                if clave not in encontrados and nombre in miembros:
                    encontrados[clave] = ArchivoKaggle(zip_path, miembros[nombre])
    faltantes = [ARCHIVOS_KAGGLE[c] for c in ARCHIVOS_KAGGLE if c not in encontrados]
    if faltantes:
        raise ErrorCargaInicial(
            f"Faltan archivos de Kaggle en {kaggle}: {faltantes}. Copie ahí los CSV de "
            "'Store Sales - Time Series Forecasting' (o el ZIP que descarga Kaggle)."
        )
    return encontrados


def huella(archivos: dict[str, ArchivoKaggle], operacion: Operacion) -> str:
    """Identifica la carga: contenido de los archivos de entrada y periodo configurado."""
    h = hashlib.sha256()
    vistos = set()
    for clave in sorted(archivos):
        archivo = archivos[clave]
        if archivo.ruta in vistos:
            continue
        vistos.add(archivo.ruta)
        with open(archivo.ruta, "rb") as f:
            for bloque in iter(lambda: f.read(1 << 20), b""):
                h.update(bloque)
    h.update(f"{operacion.corte_historico:%Y-%m-%d}|{operacion.fin_operacion:%Y-%m-%d}".encode())
    return h.hexdigest()


def _escribir_bandeja(inbox: Path, fuente: str, df: pd.DataFrame, columnas: list[str]) -> int:
    carpeta = inbox / fuente
    carpeta.mkdir(parents=True, exist_ok=True)
    dias = 0
    for fecha, grupo in df.groupby("date", sort=True):
        grupo = grupo.loc[:, columnas].copy()
        grupo["date"] = grupo["date"].dt.strftime("%Y-%m-%d")
        grupo.to_csv(carpeta / f"{fuente}_{fecha:%Y-%m-%d}.csv", index=False)
        dias += 1
    return dias


def construir_carga_inicial(rutas: Rutas, operacion: Operacion) -> dict:
    """Construye ``data/raw`` y ``data/inbox`` si todavía no existen para esta configuración."""
    archivos = localizar_archivos(rutas.kaggle)
    firma = huella(archivos, operacion)
    marcador = rutas.raw / "_carga_inicial.json"
    if marcador.exists():
        previo = json.loads(marcador.read_text(encoding="utf-8"))
        if previo.get("huella") == firma:
            logger.info("La carga inicial ya existe para esta configuración; no se repite.")
            return {**previo, "estado": "existente"}
        raise ErrorCargaInicial(
            "Ya existe una carga inicial construida con otros archivos u otro periodo. Para "
            "empezar de nuevo borre los datos de trabajo (con Docker: docker compose down -v)."
        )

    # Restos de un intento anterior que no terminó: se descartan.
    for carpeta in (rutas.raw, rutas.inbox):
        if carpeta.exists():
            shutil.rmtree(carpeta)

    corte, fin = operacion.corte_historico, operacion.fin_operacion
    resumen: dict = {
        "corte_historico": f"{corte:%Y-%m-%d}",
        "fin_operacion": f"{fin:%Y-%m-%d}",
        "huella": firma,
        "fuentes": {},
    }

    tiendas = archivos["stores"].leer()
    feriados = archivos["holidays_events"].leer()
    for nombre, df in (("stores", tiendas), ("holidays_events", feriados)):
        errores = validar_estructura(df, nombre)
        if errores:
            raise ErrorCargaInicial("; ".join(errores))
        almacen.escribir_catalogo(rutas.raw, nombre, df)

    for clave, fuente in FUENTE_DE_ARCHIVO.items():
        df = archivos[clave].leer(low_memory=False)
        errores = validar_estructura(df, fuente)
        if errores:
            raise ErrorCargaInicial("; ".join(errores))
        df["date"] = pd.to_datetime(df["date"])
        historico = df[df["date"] <= corte]
        bandeja = df[(df["date"] > corte) & (df["date"] <= fin)]
        if historico.empty:
            raise ErrorCargaInicial(f"No hay datos de '{fuente}' hasta el corte {corte:%Y-%m-%d}")
        if fuente == "ventas":
            familias = pd.DataFrame({"family": sorted(historico["family"].astype(str).unique())})
            almacen.escribir_catalogo(rutas.raw, "familias", familias)
        almacen.escribir_historico(rutas.raw, fuente, historico)
        # La bandeja conserva las columnas originales de Kaggle.
        dias = _escribir_bandeja(rutas.inbox, fuente, bandeja, list(df.columns))
        resumen["fuentes"][fuente] = {
            "filas_historico": int(len(historico)),
            "desde": f"{historico['date'].min():%Y-%m-%d}",
            "filas_bandeja": int(len(bandeja)),
            "dias_bandeja": dias,
        }
        logger.info("%s: %d filas históricas, %d días en la bandeja", fuente, len(historico), dias)

    rutas.raw.mkdir(parents=True, exist_ok=True)
    marcador.write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")
    return {**resumen, "estado": "creada"}
