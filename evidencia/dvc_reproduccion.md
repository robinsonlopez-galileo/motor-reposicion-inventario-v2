# Reproducción de un pronóstico pasado con DVC

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
