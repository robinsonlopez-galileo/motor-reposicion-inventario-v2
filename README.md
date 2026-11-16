# Motor de reposición de inventario · Corporación Favorita

Laboratorio 1 de Product Development (Maestría en Data Science, Universidad Galileo). **Versión 2:
entrega corregida según la retroalimentación de la primera revisión** (ver
[Cambios respecto a la primera entrega](DECISIONES.md#cambios-respecto-a-la-primera-entrega)).

**Integrante:** Robinson René López Hidalgo (26007448).

Cada lunes el motor pronostica las ventas diarias de los 16 días siguientes para las 54 tiendas y
33 familias de producto (1 782 series) y sugiere cuánto pedir, balanceando el costo de quedarse sin
producto (quiebre) con el de pedir de más (merma). Todo corre en Apache Airflow 3 con Docker
Compose a partir de los archivos de Kaggle *Store Sales - Time Series Forecasting*.

```
datos/kaggle/*.csv ──► carga-inicial ──► data/raw/ (histórico hasta 2016-12-31)
                                    └──► data/inbox/<fuente>/<fuente>_<día>.csv (2017, un archivo por día)

ingesta_fuentes (diario)        validar → consolidar → marcar el día como ingerido
preparacion_datos (lunes)       espera la ingesta → variables sin información futura
pronostico_semanal (lunes)      entrena candidato → evalúa vigente y baseline → decide
                                → publica pronóstico de 16 días y pedido sugerido
seguimiento_desempeno (lunes)   pronósticos publicados vs ventas reales (error y costo)
```

## Levantar el producto desde cero

Requisitos: Docker con Docker Compose v2 (en Windows, Docker Desktop con WSL 2), unos 4 GB de
memoria para Docker y el puerto 8080 libre.

```bash
git clone https://github.com/robinsonlopez-galileo/motor-reposicion-inventario-v2.git
cd motor-reposicion-inventario-v2
git checkout entrega-lab1

# 1. Datos: los archivos de Kaggle van en datos/kaggle/
#    https://www.kaggle.com/competitions/store-sales-time-series-forecasting/data
#    Sirven los CSV sueltos (train.csv, stores.csv, oil.csv, holidays_events.csv,
#    transactions.csv) o el ZIP tal como lo descarga Kaggle.
mkdir -p datos/kaggle
cp ~/Descargas/store-sales-time-series-forecasting.zip datos/kaggle/

# 2. Construir y levantar (no hace falta archivo .env)
docker compose up -d --build
```

Al levantarse, sin ninguna intervención:

1. `carga-inicial` construye la carga histórica y la bandeja a partir de los archivos de Kaggle
   (unos segundos) y termina.
2. Airflow arranca con los cuatro DAGs **activos** y, como tienen fechas de inicio y fin fijas con
   `catchup`, procesa solo todo el periodo de operación: 227 días de ingesta y 33 cortes semanales,
   del 1 de enero al 15 de agosto de 2017.

La interfaz está en http://localhost:8080 (usuario `airflow`, clave `airflow`). Para ver el avance
desde la terminal:

```bash
docker compose exec airflow-scheduler python -m motor_reposicion.cli estado
```

Cuando `pronosticos` y `seguimientos` llegan a 33, la operación terminó. Con 2 núcleos, 7 semanas
de datos reales tardaron 8 minutos; el periodo completo toma del orden de 30 a 40 minutos y menos
con más núcleos.

### Dónde quedan los resultados

Dentro del volumen `motor-datos` (`/opt/motor/data` en los contenedores):

| Carpeta | Contenido |
|---|---|
| `forecasts/pronostico_<corte>.parquet` | Venta esperada y pedido sugerido por día, tienda y familia (16 días), con el baseline como referencia |
| `forecasts/pedido_semanal_<corte>.csv` | Pedido de la semana siguiente por tienda y familia |
| `models/decisiones/<corte>.json` | Decisión de la compuerta y modelo vigente |
| `models/evaluaciones/<corte>.json` | Métricas de candidato, baseline y vigente en la validación |
| `reports/` | Seguimiento: `historial_desempeno.csv`, `resumen_por_pronostico.csv`, `resumen_general.json` |
| `control/` | Marcadores de ingesta y filas rechazadas con su motivo |

Para copiarlos a la carpeta del proyecto:

```bash
docker compose cp airflow-scheduler:/opt/motor/data/forecasts ./resultados
docker compose cp airflow-scheduler:/opt/motor/data/reports ./resultados
```

### Evaluar otro periodo

El periodo está en `config/operacion.yaml` y se puede cambiar sin tocar el código, por ejemplo con
un archivo `.env` (ver `.env.example`):

```bash
docker compose down -v                    # borra los datos de trabajo de la corrida anterior
echo "CORTE_HISTORICO=2017-03-31" >> .env
echo "FIN_OPERACION=2017-08-15"   >> .env
docker compose up -d
```

Los archivos que lleguen a la bandeja con un sufijo (`ventas_2017-05-02_correccion.csv`) se
procesan como entregas adicionales de ese día y pueden corregir fechas anteriores
([DECISIONES.md, D6](DECISIONES.md)).

## Resultados de la operación 2017

Operación simulada completa con los datos reales de Kaggle: 227 días de bandeja y 33 cortes
semanales; el seguimiento compara cada pronóstico publicado con las ventas reales
(detalle en [`evidencia/operacion_2017.md`](evidencia/operacion_2017.md)).

| Indicador (32 pronósticos, 501 días-pronóstico) | Motor | Baseline |
|---|---|---|
| Costo real del pedido sugerido (merma + quiebre) | 11 501 452 | 13 560 688 |
| WAPE de la venta esperada | 0.147 | 0.168 |
| Semanas con menor costo | 28 | 4 |

- El pedido sugerido del motor costó **15.2 % menos** que el del baseline.
- La compuerta promovió un modelo nuevo 6 veces en 33 semanas y conservó el vigente en las demás.
- En Airflow 3.3.2 (siete semanas reales) todas las ejecuciones terminaron en *success* y los
  pronósticos fueron idénticos byte a byte a los de la línea de comandos; al limpiar y reejecutar
  una semana el resultado no cambió ([`evidencia/airflow.md`](evidencia/airflow.md)).

## Reproducción de un pronóstico pasado con DVC

Ningún dato ni modelo está en Git. DVC versiona los CSV de Kaggle (`datos/kaggle.dvc`) y la etapa
`reproducir` de `dvc.yaml`, que reconstruye desde cero el pronóstico del corte indicado en
`params.yaml` con el mismo código que usan los DAGs. El remoto es una carpeta local
(`../dvc-remoto-motor`).

```bash
pip install -e ".[dvc]"
dvc pull          # o, sin acceso al remoto: copiar los CSV de Kaggle en datos/kaggle/
dvc repro         # reconstruye reproduccion/pronostico.parquet si algo cambió
dvc checkout      # recupera del caché la versión que corresponde al commit actual
```

### Evidencia de reproducción

Se ejecutó antes de publicar, en un clon nuevo del repositorio local (rama
`feature/dvc-reproduccion`, que luego se integró a `main` sin cambios en el código), con el remoto
local `../dvc-remoto-motor` al que se habían subido los datos con `dvc push`.

**1. Recuperar el pronóstico del 6 de marzo de 2017 y comprobar que está al día:**

```
$ git clone <repositorio> clon && cd clon && pip install -e ".[dvc]"
$ dvc pull
A       reproduccion/pedido_semanal.csv
A       reproduccion/pronostico.parquet
8 files fetched and 7 files added
$ dvc status
Data and pipelines are up to date.
$ md5sum reproduccion/pronostico.parquet
3c51aa97a2536f7e927759de0b013787  reproduccion/pronostico.parquet
$ dvc repro
'datos/kaggle.dvc' didn't change, skipping
Stage 'reproducir' didn't change, skipping
Data and pipelines are up to date.
```

**2. Recalcularlo desde cero a partir de los CSV de Kaggle (186 s):**

```
$ dvc repro --force
'datos/kaggle.dvc' didn't change, skipping
Running stage 'reproducir':
> python -m motor_reposicion.cli reproducir --params params.yaml --salida reproduccion
$ md5sum reproduccion/pronostico.parquet
3c51aa97a2536f7e927759de0b013787  reproduccion/pronostico.parquet
$ git status --short          # dvc.lock no cambió: el resultado es idéntico
$ dvc status
Data and pipelines are up to date.
```

**3. Pronosticar otra semana y volver al pronóstico pasado con `dvc checkout`:**

```
$ sed -i "s/2017-03-06/2017-04-03/" params.yaml && dvc repro
'datos/kaggle.dvc' didn't change, skipping
Running stage 'reproducir':
Updating lock file 'dvc.lock'
(279 s)
$ md5sum reproduccion/pronostico.parquet
45c2d3d4eb372780c74a4522d299ddbe  reproduccion/pronostico.parquet
$ python -c "import json; print(json.load(open(\"reproduccion/metricas.json\"))[\"corte\"])"
2017-04-03
$ git checkout params.yaml dvc.lock reproduccion/metricas.json && dvc checkout
M       reproduccion/pedido_semanal.csv
M       reproduccion/pronostico.parquet
$ md5sum reproduccion/pronostico.parquet
3c51aa97a2536f7e927759de0b013787  reproduccion/pronostico.parquet
$ dvc status
Data and pipelines are up to date.
```

El MD5 del pronóstico reproducido (`3c51aa97…`) es el mismo del pronóstico que publicó la operación
completa para ese corte, y el del 3 de abril (`45c2d3d4…`) también coincide con el suyo. Métricas
del corte reproducido (`reproduccion/metricas.json`): modelo vigente `boosting_2017-01-02`; en la
validación, costo 583 695 del candidato contra 722 597 del baseline (WAPE 0.149 contra 0.210);
28 512 filas de pronóstico y 13 561 586 unidades de pedido sugerido en 16 días.

Sin acceso a ese remoto (por ejemplo, en otra computadora), basta con copiar los CSV de Kaggle en
`datos/kaggle/` y ejecutar `dvc repro`: si los archivos son los mismos, el pronóstico tiene el
mismo MD5.

## Desarrollo

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                    # pruebas con datos sintéticos: no necesitan Kaggle, Airflow ni Docker
ruff check .
```

Sin Docker, la operación completa también corre desde la línea de comandos, con los mismos pasos
que los DAGs (deja los resultados en `data/`):

```bash
python -m motor_reposicion.cli operar --hasta 2017-08-15
```

La CI de GitHub Actions corre en cada Pull Request: ruff y pytest; la importación y revisión de los
DAGs con Airflow 3.3.2 (`scripts/verificar_dags.py`, que además rechaza APIs retiradas en Airflow
3); y una prueba de punta a punta que construye la imagen, levanta el `docker compose` con datos
sintéticos y espera a que todas las ejecuciones de los DAGs terminen en *success*
(`scripts/esperar_operacion.sh`).

## Estructura

```
├── src/motor_reposicion/
│   ├── carga_inicial.py     carga histórica y bandeja desde los archivos de Kaggle
│   ├── ingesta/             lectura de la bandeja, validación y almacenamiento por día
│   ├── features.py          variables con información hasta t - horizonte
│   ├── modelo/              baseline, boosting, entrenamiento, métricas, compuerta, registro
│   ├── pedido.py            pedido sugerido (newsvendor)
│   ├── seguimiento.py       pronósticos publicados vs ventas reales
│   ├── pipeline.py          pasos que llaman los DAGs y la línea de comandos
│   └── cli.py               línea de comandos (etapa de DVC, estado, operación completa)
├── dags/                    cuatro DAGs de Airflow 3 (solo orquestación)
├── config/                  periodo de operación, costos de negocio y parámetros del modelo
├── docker/ · docker-compose.yml
├── dvc.yaml · params.yaml · datos/kaggle.dvc
├── tests/                   pytest
├── scripts/                 verificación de DAGs y espera de la operación (CI)
├── evidencia/               resultados de las corridas descritas en este README
└── README.md · DECISIONES.md · AGENTS.md
```

## Problemas frecuentes

| Síntoma | Solución |
|---|---|
| `carga-inicial` termina con «Faltan archivos de Kaggle» | Copie los CSV o el ZIP en `datos/kaggle/` y vuelva a ejecutar `docker compose up -d`. |
| «Ya existe una carga inicial construida con otros archivos u otro periodo» | Cambió el periodo o los archivos: `docker compose down -v` y `docker compose up -d`. |
| Una ejecución de `ingesta_fuentes` falla en `validar` | El archivo de la bandeja no tiene la estructura esperada; el log de la tarea dice qué columna falta. |
| Airflow lento o se reinicia | Asigne al menos 4 GB a Docker (Docker Desktop → Settings → Resources) o baje `AIRFLOW_PARALELISMO` en `.env`. |
| En Linux, errores de permisos | `echo "AIRFLOW_UID=$(id -u)" >> .env` y vuelva a levantar. |
| Puerto 8080 ocupado | Libérelo o cambie el puerto publicado de `airflow-apiserver` en `docker-compose.yml`. |
