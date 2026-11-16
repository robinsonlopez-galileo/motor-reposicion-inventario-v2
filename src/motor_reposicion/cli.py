"""Línea de comandos del motor: ``python -m motor_reposicion.cli <comando>``.

Cada comando llama al mismo paso que usa el DAG correspondiente. ``reproducir`` es la etapa del
pipeline de DVC: reconstruye desde cero, en una carpeta temporal, el pronóstico de un corte pasado.
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

import pandas as pd
import yaml

from motor_reposicion import pipeline
from motor_reposicion.configuracion import RAIZ_PROYECTO, rutas_desde_entorno


def _imprimir(datos) -> None:
    print(json.dumps(datos, indent=2, ensure_ascii=False, default=str))


def reproducir(corte: str, salida: Path) -> dict:
    """Ejecuta la operación completa hasta ``corte`` en una carpeta temporal y copia a ``salida``
    el pronóstico, el pedido semanal y las métricas de ese corte."""
    corte_ts = pd.Timestamp(corte)
    if corte_ts.dayofweek != 0:
        raise SystemExit(f"El corte {corte} no es lunes: los pronósticos se publican los lunes")
    rutas = rutas_desde_entorno()
    salida.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="motor_repro_") as tmp:
        trabajo = replace(rutas, datos=Path(tmp) / "data")
        pipeline.operar(corte_ts, trabajo)
        txt = f"{corte_ts:%Y-%m-%d}"
        pronostico = trabajo.forecasts / f"pronostico_{txt}.parquet"
        semanal = trabajo.forecasts / f"pedido_semanal_{txt}.csv"
        shutil.copy2(pronostico, salida / "pronostico.parquet")
        shutil.copy2(semanal, salida / "pedido_semanal.csv")
        evaluacion = json.loads(
            (trabajo.models / "evaluaciones" / f"{txt}.json").read_text("utf-8"))
        decision = json.loads((trabajo.models / "decisiones" / f"{txt}.json").read_text("utf-8"))
        pron = pd.read_parquet(pronostico)
        metricas = {
            "corte": txt,
            "modelo_vigente": decision["vigente"]["modelo"],
            "decision": decision["decision"]["accion"],
            "validacion_candidato_costo_total": evaluacion["candidato"]["costo_total"],
            "validacion_candidato_WAPE": evaluacion["candidato"]["WAPE"],
            "validacion_baseline_costo_total": evaluacion["baseline"]["costo_total"],
            "validacion_baseline_WAPE": evaluacion["baseline"]["WAPE"],
            "filas_pronostico": int(len(pron)),
            "venta_esperada_total": round(float(pron["venta_esperada"].sum()), 1),
            "pedido_sugerido_total": int(pron["pedido_sugerido"].sum()),
        }
    (salida / "metricas.json").write_text(json.dumps(metricas, indent=2, ensure_ascii=False),
                                          encoding="utf-8")
    return metricas


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(prog="motor", description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("carga-inicial", help="Construye data/raw y la bandeja desde los CSV de Kaggle")
    p = sub.add_parser("ingesta", help="Valida y consolida la bandeja de un día")
    p.add_argument("--fecha", required=True)
    for nombre, ayuda in (("semana", "Preparación, pronóstico y seguimiento de un lunes"),
                          ("features", "Construye las variables de un corte")):
        p = sub.add_parser(nombre, help=ayuda)
        p.add_argument("--fecha", required=True)
    sub.add_parser("estado", help="Muestra el avance de la operación")
    p = sub.add_parser("operar", help="Ejecuta toda la operación hasta una fecha")
    p.add_argument("--hasta", required=True)
    p = sub.add_parser("reproducir", help="Etapa de DVC: reproduce el pronóstico de un corte")
    p.add_argument("--params", default=str(RAIZ_PROYECTO / "params.yaml"))
    p.add_argument("--salida", default=str(RAIZ_PROYECTO / "reproduccion"))
    args = parser.parse_args(argv)

    if args.comando == "carga-inicial":
        _imprimir(pipeline.carga_inicial())
    elif args.comando == "ingesta":
        rutas = rutas_desde_entorno()
        from motor_reposicion.configuracion import cargar_operacion
        from motor_reposicion.ingesta.proceso import ingerir_dia
        _imprimir(ingerir_dia(rutas, cargar_operacion(rutas).fuentes_bandeja, args.fecha))
    elif args.comando == "features":
        _imprimir({"features": pipeline.preparar_features(args.fecha)})
    elif args.comando == "semana":
        _imprimir(pipeline.semana(args.fecha))
    elif args.comando == "estado":
        _imprimir(pipeline.estado())
    elif args.comando == "operar":
        _imprimir(pipeline.operar(args.hasta))
    elif args.comando == "reproducir":
        with open(args.params, encoding="utf-8") as f:
            params = yaml.safe_load(f)
        _imprimir(reproducir(str(params["reproduccion"]["corte"]), Path(args.salida)))


if __name__ == "__main__":
    main()
