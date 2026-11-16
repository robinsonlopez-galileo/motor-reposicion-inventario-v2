# Motor de reposición de inventario · Contexto para el agente de programación

Laboratorio 1 de Product Development. Pipeline de ML orquestado con Airflow 3 que, cada lunes,
pronostica las ventas diarias de los 16 días siguientes por tienda y familia de Corporación
Favorita (datos de Kaggle *Store Sales - Time Series Forecasting*) y sugiere cuánto pedir.

## Estructura
- `src/motor_reposicion/`: toda la lógica, sin dependencias de Airflow (se prueba con pytest).
  - `carga_inicial.py`: carga histórica (`data/raw`) y bandeja diaria (`data/inbox`) desde Kaggle.
  - `ingesta/`: lectura de la bandeja, validación (estructura y filas) y almacenamiento por día.
  - `features.py`: variables con información hasta `t - horizonte` (sin fuga de información).
  - `modelo/`: baseline, gradient boosting, entrenamiento, métricas, compuerta y registro.
  - `pedido.py`: pedido sugerido (newsvendor con factor calibrado por familia).
  - `seguimiento.py`: pronósticos publicados contra ventas reales.
  - `pipeline.py`: los pasos que llaman los DAGs y la CLI. `cli.py`: línea de comandos (DVC).
- `dags/`: cuatro DAGs que solo orquestan (`airflow.sdk`).
- `config/`: periodo de operación, costos de negocio y parámetros del modelo (YAML).
- `docker/`, `docker-compose.yml`: Airflow 3.3.2 con LocalExecutor y PostgreSQL.
- `dvc.yaml`, `params.yaml`: reproducción de un pronóstico pasado con DVC.
- `tests/`: pytest con datos sintéticos (`motor_reposicion.sintetico`).

## Comandos
- Instalar: `pip install -e ".[dev]"`
- Pruebas y estilo: `pytest` y `ruff check .`
- DAGs (con Airflow 3.3.2 instalado): `python scripts/verificar_dags.py`
- Producto: copiar los CSV de Kaggle a `datos/kaggle/` y `docker compose up -d --build`
- Operación completa sin Airflow: `python -m motor_reposicion.cli operar --hasta 2017-08-15`
- Reproducir un pronóstico pasado: `dvc repro` (corte en `params.yaml`)

## Reglas
1. La lógica va en `src/motor_reposicion/`; los DAGs solo llaman funciones de `pipeline.py`.
2. Sin fuga de información: una fila de fecha `t` solo usa ventas, petróleo y transacciones hasta
   `t - horizonte`, y solo las entregas recibidas hasta el corte (`almacen.leer_fuente(hasta=)`).
   Todos los rezagos deben ser >= horizonte (lo valida `cargar_parametros`). El calendario de
   feriados sí se usa para la fecha objetivo. `tests/test_features.py` lo verifica.
3. Tareas idempotentes: cada paso recibe la fecha que procesa y solo escribe archivos con esa fecha
   en el nombre; las escrituras son atómicas (`archivos.py`). Reejecutar da el mismo resultado.
4. Airflow 3: importar de `airflow.sdk` (`dag`, `task`, `get_current_context`); fechas de inicio
   fijas con `pendulum`; `schedule`, no `schedule_interval`. Prohibido `airflow.utils.dates`,
   `days_ago`, `airflow.decorators`, `airflow.operators.*` y `execution_date`.
5. Configuración en `config/*.yaml`; nada de costos ni parámetros escritos en el código.
6. Datos y modelos nunca en Git: `data/`, `datos/kaggle/` y `reproduccion/` se versionan con DVC.
7. Toda función pública nueva lleva prueba. La CI (ruff, pytest, DAGs y Docker de punta a punta)
   debe pasar antes de integrar.
8. Ramas `feature/<tema>` o `fix/<tema>`, Pull Request a `main`, commits en español e imperativo.
