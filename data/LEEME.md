# data/

Datos de trabajo que genera el motor al correr fuera de Docker (DVC, pruebas manuales). No se
versionan con Git. En Docker Compose estos datos viven en el volumen `motor-datos`.

- `raw/`: carga histórica y entregas consolidadas por día.
- `inbox/`: bandeja con un archivo por fuente y por día.
- `processed/`, `models/`, `forecasts/`, `reports/`, `control/`: variables, modelos, pronósticos,
  seguimiento y marcadores de ingesta.
