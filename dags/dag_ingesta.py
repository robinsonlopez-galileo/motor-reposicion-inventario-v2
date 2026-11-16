"""
### Ingesta y validación de la bandeja

Cada día de la operación lee los archivos que llegaron a `data/inbox/<fuente>/`, los valida
(estructura y filas) y consolida las filas válidas en `data/raw/`. Al final deja un marcador del día
en `data/control/ingesta/`, que es lo que esperan los demás DAGs.

- Un archivo ilegible o sin las columnas esperadas hace fallar la tarea `validar` de esa fuente.
- Las filas con valores imposibles se descartan y quedan en `data/control/rechazos/`.
- Un día sin archivo de una fuente (por ejemplo, petróleo en fin de semana) no es un error.

Toda la lógica está en `motor_reposicion.ingesta`; aquí solo se orquesta.
"""
from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow.sdk import dag, get_current_context, task

from motor_reposicion import pipeline
from motor_reposicion.configuracion import cargar_operacion

OPERACION = cargar_operacion()


def _ds() -> str:
    """Fecha que procesa la ejecución (fecha lógica de Airflow)."""
    ds = get_current_context().get("ds")
    if not ds:
        raise ValueError("La ejecución no tiene fecha lógica: dispárela indicando una fecha")
    return ds


@dag(
    dag_id="ingesta_fuentes",
    description="Valida la bandeja del día y la consolida en data/raw",
    schedule="@daily",
    start_date=pendulum.instance(OPERACION.inicio.to_pydatetime(), tz="UTC"),
    end_date=pendulum.instance(OPERACION.fin_operacion.to_pydatetime(), tz="UTC"),
    catchup=True,
    max_active_runs=3,
    default_args={"owner": "motor-reposicion", "retries": 1, "retry_delay": timedelta(minutes=1)},
    tags=["ingesta", "datos"],
    doc_md=__doc__,
)
def ingesta_fuentes():
    @task
    def validar(fuente: str) -> dict:
        return pipeline.validar(fuente, _ds())

    @task
    def consolidar(validacion: dict) -> dict:
        return {**validacion, **pipeline.consolidar(validacion["fuente"], _ds())}

    @task
    def registrar_dia(resultados: list[dict]) -> dict:
        return pipeline.registrar_ingesta(_ds(), list(resultados))

    validaciones = validar.expand(fuente=list(OPERACION.fuentes_bandeja))
    registrar_dia(consolidar.expand(validacion=validaciones))


ingesta_fuentes()
