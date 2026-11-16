"""
### Seguimiento del desempeño

Cada lunes compara los 7 días que terminan ese día con todos los pronósticos publicados que los
cubrían: error de la venta esperada (MAE, RMSE, WAPE) y costo real del pedido sugerido (merma y
quiebre), junto con el del baseline publicado como referencia. Regenera los reportes acumulados
en `data/reports/`.

La lógica está en `motor_reposicion.seguimiento`.
"""
from __future__ import annotations

import os
from datetime import timedelta

import pendulum
from airflow.sdk import dag, get_current_context, task

from motor_reposicion import pipeline, seguimiento
from motor_reposicion.configuracion import cargar_costos, cargar_operacion, rutas_desde_entorno

OPERACION = cargar_operacion()
# Cada cuántos segundos revisan los sensores si su condición ya se cumple.
ESPERA = int(os.environ.get("MOTOR_POKE_INTERVAL", "60"))


def _ds() -> str:
    ds = get_current_context().get("ds")
    if not ds:
        raise ValueError("La ejecución no tiene fecha lógica: dispárela indicando una fecha")
    return ds


@dag(
    dag_id="seguimiento_desempeno",
    description="Compara pronósticos publicados con las ventas reales",
    schedule="0 0 * * 1",
    start_date=pendulum.instance(OPERACION.inicio.to_pydatetime(), tz="UTC"),
    end_date=pendulum.instance(OPERACION.fin_operacion.to_pydatetime(), tz="UTC"),
    catchup=True,
    max_active_runs=1,
    default_args={"owner": "motor-reposicion", "retries": 1, "retry_delay": timedelta(minutes=2)},
    tags=["seguimiento", "evaluacion"],
    doc_md=__doc__,
)
def seguimiento_desempeno():
    @task.sensor(poke_interval=ESPERA, timeout=12 * 3600, mode="reschedule")
    def esperar_ventas_reales() -> bool:
        return pipeline.ingesta_lista(_ds())

    @task.sensor(poke_interval=ESPERA, timeout=12 * 3600, mode="reschedule")
    def esperar_pronostico_previo() -> bool:
        return pipeline.pronostico_previo_listo(_ds())

    @task
    def evaluar_semana() -> dict:
        rutas = rutas_desde_entorno()
        detalle = seguimiento.evaluar_semana(rutas, _ds(), cargar_costos(rutas))
        return {"filas": int(len(detalle)),
                "pronosticos": sorted(detalle["corte"].unique().tolist()) if len(detalle) else []}

    @task
    def actualizar_reportes() -> dict:
        return seguimiento.consolidar(rutas_desde_entorno())

    esperas = [esperar_ventas_reales(), esperar_pronostico_previo()]
    esperas >> evaluar_semana() >> actualizar_reportes()


seguimiento_desempeno()
