"""
### Pronóstico semanal y pedido sugerido

Cada lunes (corte):

1. Entrena un candidato (gradient boosting) y el baseline con la ventana de entrenamiento.
2. Evalúa candidato, baseline y modelo vigente en la misma validación temporal.
3. Decide con el criterio de `config/model_params.yaml` (rama `promover_candidato`,
   `conservar_vigente` o `usar_baseline`) y lo registra en `data/models/decisiones/`.
4. Publica, con el modelo vigente, el pronóstico de los 16 días siguientes y el pedido sugerido en
   `data/forecasts/`.

Las ejecuciones van de una en una (`max_active_runs=1`): el vigente de una semana depende de la
decisión de la semana anterior.
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


def _aplicar_decision() -> dict:
    ti = get_current_context()["ti"]
    decision = ti.xcom_pull(task_ids="decidir", key="decision")
    return pipeline.aplicar(_ds(), decision)


@dag(
    dag_id="pronostico_semanal",
    description="Entrena, compara con el vigente y publica pronóstico y pedido sugerido",
    schedule="0 0 * * 1",
    start_date=pendulum.instance(OPERACION.inicio.to_pydatetime(), tz="UTC"),
    end_date=pendulum.instance(OPERACION.fin_operacion.to_pydatetime(), tz="UTC"),
    catchup=True,
    max_active_runs=1,
    default_args={"owner": "motor-reposicion", "retries": 1, "retry_delay": timedelta(minutes=2)},
    tags=["modelo", "pronostico"],
    doc_md=__doc__,
)
def pronostico_semanal():
    @task.sensor(poke_interval=ESPERA, timeout=12 * 3600, mode="reschedule")
    def esperar_variables() -> bool:
        return pipeline.features_listas(_ds())

    @task
    def entrenar_candidato() -> dict:
        evaluacion = pipeline.entrenar(_ds())
        return {k: evaluacion[k] for k in ("validacion", "candidato", "baseline")}

    @task
    def evaluar_vigente() -> dict:
        return pipeline.evaluar_modelo_vigente(_ds())

    @task.branch
    def decidir() -> str:
        decision = pipeline.decidir(_ds())
        get_current_context()["ti"].xcom_push(key="decision", value=decision)
        return decision["accion"]

    @task
    def promover_candidato() -> dict:
        return _aplicar_decision()

    @task
    def conservar_vigente() -> dict:
        return _aplicar_decision()

    @task
    def usar_baseline() -> dict:
        return _aplicar_decision()

    @task(trigger_rule="none_failed_min_one_success")
    def publicar_pronostico() -> dict:
        return pipeline.publicar(_ds())

    acciones = [promover_candidato(), conservar_vigente(), usar_baseline()]
    esperar_variables() >> entrenar_candidato() >> evaluar_vigente() >> decidir() >> acciones
    acciones >> publicar_pronostico()


pronostico_semanal()
