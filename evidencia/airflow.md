# Operación en Airflow 3.3.2 con los datos reales

Airflow 3.3.2 (LocalExecutor, PostgreSQL 16, FAB) con la misma configuración del
`docker-compose.yml`, ejecutado directamente sobre una máquina de 2 núcleos porque el entorno de
desarrollo no tenía acceso al registro de Docker. La imagen de Docker y el compose se prueban de
punta a punta en la CI de GitHub (job *Docker Compose de punta a punta*, con datos sintéticos).

Periodo: `CORTE_HISTORICO=2016-12-31` y `FIN_OPERACION=2017-02-14` (45 días de bandeja y 7 cortes),
con los archivos reales de Kaggle. No se disparó nada a mano: los DAGs quedaron activos al crearse
y `catchup` procesó el periodo completo.

## Resultado de `scripts/esperar_operacion.sh` (el mismo que usa la CI)

```
[519s] LISTO dias 45/45 variables 7 pronosticos 7/7 seguimientos 7/7 vigente boosting_2017-01-02
ingesta_fuentes: success=45
preparacion_datos: success=7
pronostico_semanal: success=7
seguimiento_desempeno: success=7
Operación completa: todas las ejecuciones terminaron en success
```

Tareas de `pronostico_semanal` en el primer corte (2017-01-02): no había vigente, el candidato
superó al baseline y la rama `promover_candidato` se ejecutó; las otras dos ramas quedaron
*skipped*.

```
esperar_variables     success
entrenar_candidato    success
evaluar_vigente       success
decidir               success
promover_candidato    success
conservar_vigente     skipped
usar_baseline         skipped
publicar_pronostico   success
```

## Mismo resultado que la línea de comandos

MD5 de los pronósticos publicados por Airflow y por
`python -m motor_reposicion.cli operar --hasta 2017-08-15` (operación completa de 2017):

| Pronóstico | Airflow | Línea de comandos |
|---|---|---|
| pronostico_2017-01-02.parquet | a7435f37277b | a7435f37277b |
| pronostico_2017-01-09.parquet | 4692b9b0afb4 | 4692b9b0afb4 |
| pronostico_2017-01-16.parquet | 90ded0327e50 | 90ded0327e50 |
| pronostico_2017-01-23.parquet | fb5860b3ccf7 | fb5860b3ccf7 |
| pronostico_2017-01-30.parquet | f0c15deff8c1 | f0c15deff8c1 |
| pronostico_2017-02-06.parquet | 7fa0ff6fb924 | 7fa0ff6fb924 |
| pronostico_2017-02-13.parquet | d19c75a8f8f6 | d19c75a8f8f6 |

Son idénticos byte a byte: los DAGs solo orquestan las funciones de `pipeline.py`, y los datos
posteriores a cada corte no cambian su pronóstico.

## Idempotencia

```
airflow tasks clear pronostico_semanal -s 2017-01-16 -e 2017-01-16 -y
```

La ejecución volvió a correr completa (*success*) y el pronóstico reescrito tiene el mismo MD5
(`90ded0327e50`), igual que la decisión de la compuerta.
