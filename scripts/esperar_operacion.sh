#!/usr/bin/env bash
# Espera a que Airflow (en Docker Compose) procese todo el periodo de operación y verifica que
# ninguna ejecución de los DAGs haya fallado. Lo usa la CI; también sirve en una laptop.
#
#   bash scripts/esperar_operacion.sh [segundos_maximos]
set -euo pipefail

LIMITE="${1:-3600}"
DAGS=(ingesta_fuentes preparacion_datos pronostico_semanal seguimiento_desempeno)
inicio=$(date +%s)

estado() {
  docker compose exec -T airflow-scheduler python -m motor_reposicion.cli estado 2>/dev/null
}

# Imprime cuántas ejecuciones de cada estado hay en un DAG, por ejemplo "success=45 failed=0".
ejecuciones() {
  docker compose exec -T -e PYTHONWARNINGS=ignore airflow-scheduler \
    airflow dags list-runs "$1" -o json 2>/dev/null | python3 -c '
import collections, json, sys
try:
    runs = json.load(sys.stdin)
except ValueError:
    print("sin_respuesta=1"); sys.exit()
c = collections.Counter(r["state"] for r in runs)
print(" ".join(f"{k}={v}" for k, v in sorted(c.items())) or "ninguna=0")'
}

fallidas() {
  local total=0 linea
  for dag in "${DAGS[@]}"; do
    linea=$(ejecuciones "$dag")
    if [[ "$linea" =~ failed=([0-9]+) ]]; then
      total=$((total + BASH_REMATCH[1]))
    fi
  done
  echo "$total"
}

while true; do
  transcurrido=$(( $(date +%s) - inicio ))
  if json=$(estado); then
    resumen=$(python3 - "$json" <<'PY'
import json, sys
e = json.loads(sys.argv[1])
listo = (e["dias_ingeridos"] == e["dias_operacion"]
         and e["pronosticos"] == e["cortes_semanales"]
         and e["seguimientos"] == e["cortes_semanales"])
print(("LISTO " if listo else "") + f"dias {e['dias_ingeridos']}/{e['dias_operacion']} "
      f"variables {e['variables']} pronosticos {e['pronosticos']}/{e['cortes_semanales']} "
      f"seguimientos {e['seguimientos']}/{e['cortes_semanales']} vigente {e['modelo_vigente']}")
PY
)
    echo "[${transcurrido}s] $resumen"
    if [[ "$resumen" == LISTO* ]]; then
      error=0
      for dag in "${DAGS[@]}"; do
        linea=$(ejecuciones "$dag")
        echo "$dag: $linea"
        [[ "$linea" =~ ^success=[0-9]+$ ]] || error=1
      done
      echo "$json"
      if (( error )); then
        echo "Hay ejecuciones que no terminaron en success"; exit 1
      fi
      echo "Operación completa: todas las ejecuciones terminaron en success"
      exit 0
    fi
  else
    echo "[${transcurrido}s] Airflow todavía no responde"
  fi
  n=$(fallidas)
  if [[ "$n" != "0" ]]; then
    echo "Hay $n ejecuciones fallidas"; exit 1
  fi
  if (( transcurrido > LIMITE )); then
    echo "Tiempo agotado (${LIMITE}s)"; exit 1
  fi
  sleep 20
done
