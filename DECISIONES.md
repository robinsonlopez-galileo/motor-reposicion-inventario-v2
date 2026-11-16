# DECISIONES.md · Decisiones técnicas y de producto

Cada decisión tiene el contexto, las alternativas que se consideraron y la justificación. Las cifras
vienen de la operación simulada de enero a agosto de 2017 con los datos reales de Kaggle
(`evidencia/operacion_2017.md`).

## Índice por requisito del enunciado

| Requisito | Decisiones |
|---|---|
| Datos fuera de Git y reproducción de un pronóstico pasado con DVC | [D16](#d16--dvc) |
| Ingesta y validación de la bandeja | [D1](#d1--carga-histórica-y-periodo-de-operación), [D2](#d2--bandeja-y-catálogos), [D6](#d6--correcciones-de-datos-ya-entregados), [D7](#d7--validación-de-la-bandeja) |
| Preparación de datos sin fuga de información | [D3](#d3--disponibilidad-temporal-de-la-información-sin-fuga), [D4](#d4--variables-del-modelo), [D5](#d5--días-con-la-tienda-cerrada) |
| Baseline, modelo de ML y validación temporal | [D8](#d8--validación-temporal-y-ventana-de-entrenamiento), [D10](#d10--baseline-y-modelo-de-machine-learning) |
| Pronóstico y pedido sugerido | [D9](#d9--pedido-sugerido), [D11](#d11--criterio-de-reemplazo-del-modelo) |
| Métricas técnicas y de negocio, seguimiento del desempeño | [D12](#d12--métricas) |
| Airflow 3 con Docker Compose | [D13](#d13--orquestación-con-airflow-3), [D14](#d14--idempotencia), [D15](#d15--docker-compose) |
| Repositorio, CI y archivo de contexto del agente | [D17](#d17--repositorio-ci-y-archivo-de-contexto) |

## Cambios respecto a la primera entrega

| Retroalimentación | Qué se hizo |
|---|---|
| No cuenta con tags | Tag anotado `entrega-lab1` sobre `main` (es la versión que se evalúa). |
| No cuenta con PRs | Cada parte entró a `main` por su propio Pull Request desde una rama `feature/*` o `docs/*`. |
| CI falla | El `pyproject.toml` tenía un *build-backend* inexistente y la instalación fallaba en el primer paso. Ahora la CI instala, corre ruff y 54 pruebas, importa los DAGs con Airflow 3.3.2 y levanta el `docker compose` completo de punta a punta. |
| Datos subidos a Git | Se quitaron Git LFS y todos los datos del repositorio. Los CSV de Kaggle y lo que genera el motor se versionan con DVC (D16); Git solo guarda los archivos `.dvc` y `dvc.lock`. |
| DAG con funciones no compatibles con Airflow 3 | Los DAGs usaban `airflow.utils.dates.days_ago` (retirado en Airflow 3), `airflow.decorators` y `airflow.operators.python`, y el compose usaba el comando `webserver` de Airflow 2. Ahora todo usa `airflow.sdk`, fechas fijas con `pendulum`, `api-server` y `dag-processor`, y la CI rechaza cualquier API retirada (D13). |

Además se corrigieron errores de fondo que había en la primera versión: los rezagos de 7 y 14 días
usaban ventas que no se conocen al pronosticar 16 días, el criterio de reemplazo comparaba métricas
de ventanas distintas, el baseline nunca se comparaba, la ingesta fallaba los días sin archivo
(petróleo en fin de semana) y el enlace simbólico `best_model.pkl` no funciona en Windows.

---

## D1 · Carga histórica y periodo de operación

**Decisión.** Las ventas hasta el 31 de diciembre de 2016 forman la carga histórica (`data/raw/`).
Los días siguientes, hasta el 15 de agosto de 2017 (último día de `train.csv`), se dejan en la
bandeja (`data/inbox/`), un archivo por fuente y por día. Las dos fechas están en
`config/operacion.yaml` y se pueden cambiar con `CORTE_HISTORICO` y `FIN_OPERACION`.

**Alternativas.** Usar todo `train.csv` como histórico (no habría operación que simular); un corte
en 2015 (menos historia para la ventana de entrenamiento y los rezagos).

**Justificación.** Cuatro años de historia alcanzan para la ventana de entrenamiento de 365 días,
la validación y los rezagos más largos (84 días + horizonte). Los 227 días de 2017 permiten
operar 33 semanas. Que el periodo sea configurable permite al equipo docente evaluar sobre otro
periodo sin tocar el código.

## D2 · Bandeja y catálogos

**Decisión.** La carga inicial (`carga_inicial.py`) lee los CSV de Kaggle (sueltos o el ZIP de la
competencia) y escribe la bandeja con el formato original de Kaggle:
`inbox/<fuente>/<fuente>_<AAAA-MM-DD>.csv` para ventas, petróleo y transacciones. Las tiendas y el
calendario de feriados son catálogos y se cargan completos. Las familias válidas salen del histórico.

**Alternativas.** Feriados también por día en la bandeja (el calendario de los días futuros no se
conocería y el modelo no podría usar feriados del horizonte); un solo archivo por semana.

**Justificación.** Un archivo por día es lo que entrega un sistema de origen y hace natural la
ingesta diaria. El calendario de feriados se publica con anticipación, así que usarlo para el
horizonte no es información futura. La carga inicial es idempotente: si ya existe con los mismos
archivos (hash SHA-256) y el mismo periodo, no hace nada; si cambió, se detiene con un mensaje
claro en lugar de mezclar dos cargas.

## D3 · Disponibilidad temporal de la información (sin fuga)

**Decisión.** Para una fila de fecha `t`, todas las variables usan solo datos hasta `t - 16`
(el horizonte). Así, para cualquier día del horizonte (corte + 1 … corte + 16) se usan solo datos
hasta el corte, y las filas de entrenamiento se construyen con exactamente la misma regla. Además,
las fuentes se leen "al cierre del corte": solo con las entregas recibidas hasta ese día
(`almacen.leer_fuente(hasta=corte)`). Todos los rezagos deben ser mayores o iguales al horizonte;
`cargar_parametros` rechaza una configuración que no lo cumpla.

**Alternativas.** Rezagos de 1, 7 y 14 días con pronóstico recursivo (los errores se acumulan y el
modelo entrena con información distinta a la que tiene al predecir); un modelo por día del horizonte
(16 modelos, 16 veces el costo); usar las promociones del día objetivo, que Kaggle publica en
`test.csv`.

**Justificación.** Con un solo desplazamiento igual al horizonte no hay diferencia entre entrenar y
predecir, y la regla es fácil de verificar: `test_no_usa_informacion_posterior_al_corte` altera
todas las ventas posteriores al corte y comprueba que las variables no cambian. Las promociones del
día objetivo llegan en el archivo de ventas de ese día, es decir, después del corte; por eso no se
usan (sería una mejora si el sistema de origen entregara la planificación de promociones por
adelantado).

## D4 · Variables del modelo

**Decisión.** Por tienda y familia: rezagos de 21, 28, 35 y 42 días (mismo día de la semana),
medias móviles de 7, 28 y 84 días hasta `t - 16`, proporción de días sin venta, el valor del
baseline, la variación de 28 días del precio del petróleo, la media de 28 días de transacciones de
la tienda, el calendario (día de la semana y del mes, mes, semana, fin de semana, días de pago 15 y
fin de mes) y feriados nacionales, regionales (estado de la tienda) y locales (ciudad), eventos y
días laborables recuperados. Tienda, familia, cluster y tipo de tienda son categóricas.

**Alternativas.** El nivel del precio del petróleo, como en la primera versión.

**Justificación.** Al probar con los datos reales, el nivel del petróleo funcionaba como un reloj:
los precios más altos solo aparecían en las últimas semanas de entrenamiento, que incluían el 1 de
enero (tiendas cerradas). El modelo aprendió "petróleo alto = ventas casi nulas" y subestimó las
ventas de enero a la mitad (WAPE de 0.39 contra 0.20 del baseline). Con la variación del precio el
problema desaparece.

## D5 · Días con la tienda cerrada

**Decisión.** Las filas de un día en que la tienda no vendió nada en ninguna familia (por ejemplo,
el 1 de enero) se marcan con `tienda_cerrada` y no se usan para entrenar ni para evaluar.

**Alternativas.** Tratarlas como demanda cero; quitar solo el 1 de enero.

**Justificación.** Una tienda cerrada no es demanda cero: enseñarle eso al modelo baja todas las
predicciones. La regla general (venta total de la tienda igual a cero) cubre cierres que no están en
el calendario.

## D6 · Correcciones de datos ya entregados

**Decisión.** La entrega de un día puede traer filas de fechas anteriores, en el archivo principal o
en un archivo adicional con sufijo (`ventas_2017-03-10_correccion.csv`). Las filas del día se
guardan en `raw/<fuente>/dias/<fecha>.parquet` y las de fechas anteriores en
`raw/<fuente>/correcciones/<fecha>.parquet`. Al leer, ante claves repetidas gana la última entrega.

**Alternativas.** Reescribir el histórico consolidado en cada ingesta (en la primera versión, un
solo parquet de 2.6 millones de filas que todas las tareas reescribían); conservar ambas versiones
con fecha de ingesta.

**Justificación.** Cada ingesta solo escribe archivos de su propio día, así que se pueden procesar
varios días en paralelo y reintentar sin riesgo. Al reconstruir lo que se sabía al cierre de un
corte, las correcciones recibidas después no se usan (no hay fuga), como verifica
`test_correccion_reemplaza_el_dato_anterior_desde_su_entrega`.

## D7 · Validación de la bandeja

**Decisión.** Dos niveles. Si un archivo no se puede leer, está vacío o le faltan columnas, la tarea
`validar` falla y el día no se marca como ingerido: el resto del flujo espera hasta que alguien lo
revise. Las filas con valores imposibles (fecha inválida, tienda o familia desconocida, ventas o
transacciones negativas o no numéricas, promoción inválida) se descartan y se guardan con su motivo
en `data/control/rechazos/`. Las filas repetidas en un archivo conservan la última. Un día sin
archivo (petróleo en fin de semana, un cierre) no es un error.

**Alternativas.** Rechazar el archivo completo por una sola fila mala; aceptar todo y limpiar al
construir variables.

**Justificación.** Un archivo sin estructura es un problema del sistema de origen que hay que ver;
una fila mala no debe frenar la operación de 1 782 series. El motivo de cada rechazo queda
registrado para auditoría.

## D8 · Validación temporal y ventana de entrenamiento

**Decisión.** Para cada corte, los 28 días que terminan en el corte son la validación y los 365
días anteriores, el entrenamiento. Candidato, baseline y modelo vigente se evalúan sobre las mismas
filas de validación. El candidato no se reentrena con la validación antes de publicar.

**Alternativas.** Validación aleatoria (invalida resultados en series de tiempo); k-fold cronológico
(k entrenamientos por semana); reentrenar con entrenamiento + validación antes de publicar; una
ventana de 730 días.

**Justificación.** Como el candidato no ve la validación, la semana siguiente el vigente se evalúa
sobre días que tampoco vio: la comparación es justa (en la primera versión se comparaba el RMSE del
candidato con un RMSE guardado de otra ventana). Se probó una ventana de 730 días en las primeras
siete semanas de 2017: el costo real del pedido en el seguimiento fue mayor (2.14 millones contra
2.00 millones con 365 días) y cada entrenamiento tardó el doble, así que se mantuvo 365.

## D9 · Pedido sugerido

**Decisión.** Problema del newsvendor: con costo de quiebre `Cu = 0.30` y de merma `Co = 0.10` por
unidad (`config/business_costs.yaml`), la cantidad óptima es el cuantil `q* = Cu / (Cu + Co) = 0.75`
de la demanda. El modelo pronostica la venta esperada y, por familia, se calibra un factor `k` en la
validación como el cuantil 0.75 del cociente real/pronóstico **ponderado por el pronóstico**. El
pedido es `k × pronóstico` redondeado al entero más cercano, con `k` entre 0.5 y 3. Los factores se recalibran cada semana,
también los del modelo vigente cuando se conserva. Además del pedido diario de 16 días se publica el
pedido semanal (suma de los 7 días siguientes al corte) por tienda y familia.

**Alternativas.** Pedir la venta esperada (subestima cuando el quiebre cuesta más que la merma);
desviación estándar fija del 30 % y distribución normal, como en la primera versión (supuesto sin
respaldo en los datos); cuantil sin ponderar; un modelo de cuantiles.

**Justificación.** El costo de una fila es `pronóstico × [Co (k − x)+ + Cu (x − k)+]` con
`x = real / pronóstico`, y su suma se minimiza exactamente con el cuantil ponderado (lo verifica
`test_factores_minimizan_el_costo_de_validacion`). El cuantil sin ponderar dejaba que las series de
poco volumen y mucha varianza definieran el factor de las grandes. Recalibrar el factor del vigente
evita usar durante semanas un factor calibrado en otra época del año (el modelo del 2 de enero
llegó a usar hasta marzo factores calibrados en plena Navidad). Se redondea en lugar de usar el
techo porque, con el techo, un producto con 0.05 unidades esperadas por día recibía 1 unidad
diaria; en la validación el redondeo además tuvo un costo algo menor.

## D10 · Baseline y modelo de machine learning

**Decisión.** Baseline: promedio de las últimas 8 semanas del mismo día de la semana, con la misma
regla de información (`t - 16`). Modelo: `HistGradientBoostingRegressor` de scikit-learn con pérdida
Poisson, variables categóricas nativas y parámetros en `config/model_params.yaml`.

**Alternativas.** LightGBM (la primera versión); Prophet o SARIMA por serie; XGBoost.

**Justificación.** HistGradientBoosting es el mismo tipo de algoritmo que LightGBM (boosting con
histogramas) pero viene con scikit-learn, que ya está en las restricciones oficiales de Airflow
3.3.2: no agrega dependencias del sistema (LightGBM necesita `libgomp`) ni conflictos de versiones en
la imagen. La pérdida Poisson respeta que las ventas no son negativas. Prophet y SARIMA exigirían
1 782 modelos por semana. En la operación de 2017 el motor tuvo un WAPE de 0.147 contra 0.168 del
baseline y un costo 15.2 % menor; fue mejor en 14 de los 16 días del horizonte (los domingos, días 6
y 13, el baseline tuvo menos error), lo que queda como oportunidad de mejora
(`evidencia/operacion_2017.md`).

## D11 · Criterio de reemplazo del modelo

**Decisión.** Cada lunes:
1. Si el candidato no tiene menor costo total que el baseline en la validación, no se promueve.
2. Si no hay modelo vigente, el candidato pasa a ser el vigente; si no superó al baseline, el
   vigente es el baseline (el motor nunca se queda sin modelo).
3. Si hay vigente, el candidato lo reemplaza solo si baja el costo total al menos 2 %.

La decisión queda en `data/models/decisiones/<corte>.json` con las métricas de los tres modelos. El
vigente de una semana es el que dejó la última decisión anterior a ese corte.

**Alternativas.** Reemplazar siempre (el modelo cambia por ruido); umbral sobre RMSE (no mide lo
que le importa al negocio); exigir significancia estadística.

**Justificación.** La métrica de la decisión es la misma que paga la operación: el costo de merma
y quiebre del pedido sugerido. El umbral del 2 % evita cambiar de modelo por diferencias pequeñas
(en 2017 se promovió 6 veces en 33 semanas). Leer el vigente desde el registro de decisiones hace
que reejecutar una semana dé exactamente el mismo resultado.

## D12 · Métricas

**Técnicas:** MAE, RMSE y WAPE (error absoluto total sobre venta total, comparable entre familias
de distinto volumen). **De negocio:** costo de merma (unidades sobrantes × 0.10), costo de quiebre
(unidades faltantes × 0.30) y costo total del pedido sugerido. El seguimiento las calcula con las
ventas reales para el pronóstico publicado y para el baseline publicado junto a él.

## D13 · Orquestación con Airflow 3

**Decisión.** Cuatro DAGs con `airflow.sdk`, fechas de inicio y fin fijas (el periodo de operación)
y `catchup=True`, activos al crearse:

| DAG | Horario | Qué hace |
|---|---|---|
| `ingesta_fuentes` | diario | `validar` → `consolidar` por fuente (tareas mapeadas) → `registrar_dia` |
| `preparacion_datos` | lunes | espera la ingesta hasta el corte → construye variables |
| `pronostico_semanal` | lunes | espera variables → entrena → evalúa vigente → `decidir` (rama) → promover / conservar / usar baseline → publica |
| `seguimiento_desempeno` | lunes | espera ventas reales y el pronóstico anterior → evalúa la semana → actualiza reportes |

Las dependencias entre DAGs se resuelven con sensores TaskFlow (`@task.sensor`, modo
*reschedule*) que revisan marcadores en disco: el marcador de ingesta de cada día, el archivo de
variables y el pronóstico publicado. `pronostico_semanal` y `seguimiento_desempeno` corren de una
ejecución a la vez porque cada semana depende de la anterior; la ingesta procesa hasta 3 días en
paralelo.

**Alternativas.** Un solo DAG diario con todo; `ExternalTaskSensor` (exige alinear fechas lógicas
entre horarios distintos); Assets de Airflow 3 (las ejecuciones disparadas por un asset no tienen
fecha lógica, y el corte es justamente esa fecha).

**Justificación.** Cada responsabilidad del enunciado tiene su DAG. Los marcadores hacen explícito
"qué datos tienen que existir" y se prueban sin Airflow. Con `catchup` y los DAGs activos, al
levantar el compose el periodo completo se procesa solo, sin intervención manual. Se verificó con
Airflow 3.3.2 y los datos reales: 45 ejecuciones de ingesta y 7 de cada DAG semanal en *success*,
con pronósticos idénticos byte a byte a los de la línea de comandos (`evidencia/airflow.md`).

## D14 · Idempotencia

**Decisión.** Cada paso recibe la fecha que procesa y solo escribe archivos con esa fecha en el
nombre; las escrituras son atómicas (archivo temporal y renombre). El vigente se lee del registro de
decisiones anteriores al corte, no de un "último modelo".

**Justificación.** Reintentos y *backfills* sin efectos secundarios: en Airflow se limpió una semana
ya procesada y al reejecutarla el pronóstico y la decisión quedaron idénticos.

## D15 · Docker Compose

**Decisión.** Airflow 3.3.2 con LocalExecutor y PostgreSQL 16.9; servicios `airflow-init`,
`carga-inicial` (una vez), `airflow-apiserver`, `airflow-scheduler` y `airflow-dag-processor`. El
código, los DAGs y la configuración viajan dentro de la imagen; los datos de trabajo, en el volumen
`motor-datos`; los CSV de Kaggle se montan de `datos/kaggle/` en solo lectura. Todos los valores
tienen un valor por defecto: no hace falta crear `.env`.

**Alternativas.** CeleryExecutor con Redis (la primera versión: más servicios y memoria sin
beneficio en una sola máquina); montar todo el proyecto en el contenedor (lo que corre depende de la
laptop y no del tag); carpeta del host para los datos (problemas de permisos en Linux).

**Justificación.** Menos piezas que fallen al levantar desde cero. La CI construye la imagen, la
levanta con datos sintéticos y espera a que todas las ejecuciones terminen en *success*.

## D16 · DVC

**Decisión.** DVC con un remoto en una carpeta local (`../dvc-remoto-motor`, configurable). Se
versionan los CSV de Kaggle (`datos/kaggle.dvc`) y la etapa `reproducir` de `dvc.yaml`, que
reconstruye desde cero el pronóstico de un corte pasado (`params.yaml`) y guarda pronóstico, pedido
y métricas.

**Alternativas.** Google Drive (la primera versión: exige autenticación OAuth y otra persona no puede
descargar sin permisos); DagsHub o S3 (cuentas adicionales); Git LFS (datos en Git, que el
enunciado prohíbe).

**Justificación.** Una carpeta local es la opción vista en clase y no depende de credenciales. La
etapa usa la misma función que los DAGs, así que reproducir con DVC es reproducir el producto. La
evidencia (comandos y resultados, con hashes idénticos) está en el README.

## D17 · Repositorio, CI y archivo de contexto

**Decisión.** El trabajo se divide en ramas `feature/*` y `docs/*` que se encadenan; cada una entra
a `main` por Pull Request solo con la CI en verde, y la versión entregada se marca con el tag anotado
`entrega-lab1`. La CI tiene tres jobs: `pruebas` (ruff y pytest), `dags` (importa y revisa los DAGs
con Airflow 3.3.2 y rechaza APIs retiradas) y `docker` (levanta el compose con datos sintéticos y
exige *success* en todas las ejecuciones). El archivo de contexto para el agente de programación es
`AGENTS.md`.

**Alternativas.** Un solo commit o un solo PR con todo (es lo que señaló la retroalimentación);
una CI que solo corra pytest (no habría detectado los DAGs incompatibles con Airflow 3 ni un compose
que no levanta); `CLAUDE.md` como archivo de contexto.

**Justificación.** Los PR por tema dejan ver cómo se construyó el motor y permiten revisar cada parte
por separado. La CI prueba lo que el equipo docente va a hacer: levantar el compose y ejecutar el
flujo sin intervención. Cada rama debe ser autosuficiente: cuando un archivo que usa la CI (las
restricciones de Airflow) llegaba en un PR posterior, la CI del anterior fallaba. `AGENTS.md` es un
formato abierto que leen varios agentes de programación (Claude Code, Codex, OpenCode).
