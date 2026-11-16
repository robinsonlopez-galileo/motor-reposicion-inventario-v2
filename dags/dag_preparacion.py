"""
### Preparación de los datos para el modelo

Cada lunes (corte semanal) espera a que todos los días hasta el corte estén ingeridos y construye
las variables del modelo en `data/processed/features_<corte>.parquet`: filas de entrenamiento,
validación y los 16 días del horizonte, todas con información conocida hasta el corte.

La lógica está en `motor_reposicion.features`.
"""
from __future__ import annotations

import os
from datetime import timedelta

import pendulum
from airflow.sdk import dag, get_current_context, task

from motor_reposicion import pipeline
from motor_reposicion.configuracion import cargar_operacion

OPERACION = cargar_operacion()
# Cada cuántos segundos revisan los sensores si su condición ya se cumple.
ESPERA = int(os.environ.get("MOTOR_POKE_INTERVAL", "60"))


def _ds() -> str:
    ds = get_current_context().get("ds")
    if not ds:
        raise ValueError("La ejecución no tiene fecha lógica: dispárela indicando una fecha")
    return ds


@dag(
    dag_id="preparacion_datos",
    description="Construye las variables del corte semanal",
    schedule="0 0 * * 1",
    start_date=pendulum.instance(OPERACION.inicio.to_pydatetime(), tz="UTC"),
    end_date=pendulum.instance(OPERACION.fin_operacion.to_pydatetime(), tz="UTC"),
    catchup=True,
    max_active_runs=2,
    default_args={"owner": "motor-reposicion", "retries": 1, "retry_delay": timedelta(minutes=2)},
    tags=["features", "datos"],
    doc_md=__doc__,
)
def preparacion_datos():
    @task.sensor(poke_interval=ESPERA, timeout=12 * 3600, mode="reschedule")
    def esperar_ingesta() -> bool:
        return pipeline.ingesta_lista(_ds())

    @task
    def construir_variables() -> str:
        return pipeline.preparar_features(_ds())

    esperar_ingesta() >> construir_variables()


preparacion_datos()
