"""Datos sintéticos con el formato de Kaggle para probar el motor sin los archivos reales."""
from __future__ import annotations

import os

# Con datos tan pequeños un solo hilo es más rápido y evita competir por CPU en la CI.
os.environ.setdefault("OMP_NUM_THREADS", "1")

import shutil  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
import yaml  # noqa: E402

from motor_reposicion.configuracion import RAIZ_PROYECTO, Rutas  # noqa: E402
from motor_reposicion.sintetico import CORTE, FIN, escribir_kaggle  # noqa: E402


def escribir_config(carpeta: Path) -> Path:
    """Configuración del repositorio con un periodo y un modelo pequeños para las pruebas."""
    shutil.copytree(RAIZ_PROYECTO / "config", carpeta)
    operacion = yaml.safe_load((carpeta / "operacion.yaml").read_text("utf-8"))
    operacion.update({"corte_historico": CORTE, "fin_operacion": FIN})
    (carpeta / "operacion.yaml").write_text(yaml.safe_dump(operacion), "utf-8")
    modelo = yaml.safe_load((carpeta / "model_params.yaml").read_text("utf-8"))
    modelo["modelo"]["max_iter"] = 30
    modelo["training_window_days"] = 90
    modelo["validation_days"] = 14
    (carpeta / "model_params.yaml").write_text(yaml.safe_dump(modelo), "utf-8")
    return carpeta


def preparar_proyecto(carpeta: Path, monkeypatch: pytest.MonkeyPatch) -> Rutas:
    """Proyecto aislado: datos sintéticos de Kaggle, configuración de prueba y carpeta de datos."""
    kaggle = escribir_kaggle(carpeta / "kaggle")
    config = escribir_config(carpeta / "config")
    datos = carpeta / "data"
    for variable, valor in (("MOTOR_DATA_DIR", datos), ("MOTOR_KAGGLE_DIR", kaggle),
                            ("MOTOR_CONFIG_DIR", config)):
        monkeypatch.setenv(variable, str(valor))
    monkeypatch.delenv("CORTE_HISTORICO", raising=False)
    monkeypatch.delenv("FIN_OPERACION", raising=False)
    return Rutas(datos=datos, kaggle=kaggle, config=config)


@pytest.fixture
def rutas(tmp_path, monkeypatch) -> Rutas:
    return preparar_proyecto(tmp_path, monkeypatch)
