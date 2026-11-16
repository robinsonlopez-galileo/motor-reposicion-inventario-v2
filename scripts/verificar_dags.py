"""Verifica que los DAGs cargan en Airflow 3 y tienen la estructura esperada.

Uso (con Airflow 3.3.2 instalado): ``python scripts/verificar_dags.py``. La CI lo ejecuta en cada
Pull Request. Falla si algún DAG no importa, si usa APIs retiradas en Airflow 3 o si cambia la
estructura de tareas.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CARPETA = RAIZ / "dags"

PROHIBIDO = [
    r"airflow\.utils\.dates",
    r"\bdays_ago\b",
    r"airflow\.decorators",
    r"airflow\.operators\.",
    r"\bschedule_interval\b",
    r"\bexecution_date\b",
    r"airflow\.models\.dag\b",
]

ESPERADO = {
    "ingesta_fuentes": ("@daily", {"validar", "consolidar", "registrar_dia"}),
    "preparacion_datos": ("0 0 * * 1", {"esperar_ingesta", "construir_variables"}),
    "pronostico_semanal": ("0 0 * * 1", {
        "esperar_variables", "entrenar_candidato", "evaluar_vigente", "decidir",
        "promover_candidato", "conservar_vigente", "usar_baseline", "publicar_pronostico"}),
    "seguimiento_desempeno": ("0 0 * * 1", {
        "esperar_ventas_reales", "esperar_pronostico_previo", "evaluar_semana",
        "actualizar_reportes"}),
}


def main() -> int:
    errores: list[str] = []
    for archivo in sorted(CARPETA.glob("*.py")):
        texto = archivo.read_text(encoding="utf-8")
        for patron in PROHIBIDO:
            if re.search(patron, texto):
                errores.append(f"{archivo.name}: usa '{patron}', que no corresponde a Airflow 3")
        if "from airflow.sdk import" not in texto:
            errores.append(f"{archivo.name}: no importa desde airflow.sdk")

    import airflow
    from airflow.dag_processing.dagbag import DagBag

    if not airflow.__version__.startswith("3."):
        errores.append(f"Se esperaba Airflow 3 y está instalado {airflow.__version__}")
    bolsa = DagBag(dag_folder=str(CARPETA))
    for ruta, error in bolsa.import_errors.items():
        errores.append(f"Error al importar {ruta}: {error}")

    for dag_id, (horario, tareas) in ESPERADO.items():
        dag = bolsa.dags.get(dag_id)
        if dag is None:
            errores.append(f"No se encontró el DAG {dag_id}")
            continue
        if str(dag.schedule) != horario:
            errores.append(f"{dag_id}: horario {dag.schedule!r}, se esperaba {horario!r}")
        encontradas = set(dag.task_ids)
        if encontradas != tareas:
            errores.append(f"{dag_id}: tareas {sorted(encontradas)}, se esperaba {sorted(tareas)}")
        if not dag.catchup:
            errores.append(f"{dag_id}: debe tener catchup=True para procesar el periodo completo")
        print(f"OK {dag_id}: {dag.schedule}, {len(encontradas)} tareas, "
              f"desde {dag.start_date:%Y-%m-%d} hasta {dag.end_date:%Y-%m-%d}")

    extra = set(bolsa.dags) - set(ESPERADO)
    if extra:
        errores.append(f"DAGs inesperados: {sorted(extra)}")
    for e in errores:
        print("ERROR", e)
    print("Verificación de DAGs:", "falló" if errores else "correcta")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
