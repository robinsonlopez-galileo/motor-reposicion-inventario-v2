"""Pasos del motor. Los DAGs de Airflow y la línea de comandos (usada por DVC) llaman a estas mismas
funciones, de modo que la lógica existe en un solo lugar.

Todos los pasos reciben la fecha que procesan (``ds`` en Airflow) y solo escriben archivos con esa
fecha en el nombre: volver a ejecutarlos produce el mismo resultado.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from motor_reposicion import seguimiento
from motor_reposicion.archivos import escribir_csv, escribir_parquet
from motor_reposicion.carga_inicial import construir_carga_inicial
from motor_reposicion.configuracion import (
    Rutas,
    cargar_costos,
    cargar_operacion,
    cargar_parametros,
    rutas_desde_entorno,
)
from motor_reposicion.features import cargar_fuentes, construir_dataset
from motor_reposicion.ingesta import proceso
from motor_reposicion.modelo import compuerta, registro
from motor_reposicion.modelo.entrenamiento import dividir, entrenar_candidato, evaluar_vigente
from motor_reposicion.pedido import calcular_pedido, pedido_semanal

logger = logging.getLogger(__name__)


def _f(fecha) -> pd.Timestamp:
    return pd.Timestamp(fecha).normalize()


def _rutas(rutas: Rutas | None) -> Rutas:
    return rutas or rutas_desde_entorno()


# --------------------------------------------------------------------------- carga e ingesta
def carga_inicial(rutas: Rutas | None = None) -> dict:
    rutas = _rutas(rutas)
    return construir_carga_inicial(rutas, cargar_operacion(rutas))


def validar(fuente: str, fecha, rutas: Rutas | None = None) -> dict:
    return proceso.validar_entrega(_rutas(rutas), fuente, _f(fecha))


def consolidar(fuente: str, fecha, rutas: Rutas | None = None) -> dict:
    return proceso.consolidar_entrega(_rutas(rutas), fuente, _f(fecha))


def registrar_ingesta(fecha, resultados: list[dict], rutas: Rutas | None = None) -> dict:
    return proceso.registrar_ingesta(_rutas(rutas), _f(fecha), resultados)


def ingesta_lista(fecha, rutas: Rutas | None = None) -> bool:
    """``True`` cuando todos los días de la operación hasta ``fecha`` ya se ingirieron."""
    rutas = _rutas(rutas)
    operacion = cargar_operacion(rutas)
    faltantes = proceso.dias_sin_ingerir(rutas, operacion.inicio, _f(fecha))
    if faltantes:
        logger.info("Faltan %d días por ingerir (primero: %s)", len(faltantes), faltantes[0])
    return not faltantes


# --------------------------------------------------------------------------- preparación
def ruta_features(rutas: Rutas, fecha) -> Path:
    return rutas.processed / f"features_{_f(fecha):%Y-%m-%d}.parquet"


def preparar_features(fecha, rutas: Rutas | None = None) -> str:
    rutas = _rutas(rutas)
    costos = cargar_costos(rutas)
    params = cargar_parametros(rutas, costos.horizonte)
    dataset = construir_dataset(cargar_fuentes(rutas, _f(fecha)), costos.horizonte, params)
    ruta = escribir_parquet(dataset, ruta_features(rutas, fecha))
    logger.info("Variables del corte %s: %d filas", f"{_f(fecha):%Y-%m-%d}", len(dataset))
    return str(ruta)


def features_listas(fecha, rutas: Rutas | None = None) -> bool:
    return ruta_features(_rutas(rutas), fecha).exists()


def _dataset(rutas: Rutas, fecha) -> pd.DataFrame:
    return pd.read_parquet(ruta_features(rutas, fecha))


# --------------------------------------------------------------------------- modelo
def entrenar(fecha, rutas: Rutas | None = None) -> dict:
    """Entrena el candidato y el baseline del corte y guarda sus métricas de validación."""
    rutas = _rutas(rutas)
    costos = cargar_costos(rutas)
    params = cargar_parametros(rutas, costos.horizonte)
    resultado = entrenar_candidato(_dataset(rutas, fecha), params, costos)
    registro.guardar_modelo(resultado.candidato,
                            registro.ruta_candidato(rutas.models, fecha, "boosting"))
    registro.guardar_modelo(resultado.baseline,
                            registro.ruta_candidato(rutas.models, fecha, "baseline"))
    evaluacion = {"corte": f"{_f(fecha):%Y-%m-%d}", **resultado.resumen()}
    registro.guardar_evaluacion(rutas.models, fecha, evaluacion)
    return evaluacion


def evaluar_modelo_vigente(fecha, rutas: Rutas | None = None) -> dict:
    """Evalúa el modelo vigente al inicio de la semana en la misma validación del candidato."""
    rutas = _rutas(rutas)
    costos = cargar_costos(rutas)
    params = cargar_parametros(rutas, costos.horizonte)
    vigente = registro.vigente_antes_de(rutas.models, fecha)
    evaluacion = registro.leer_evaluacion(rutas.models, fecha)
    metricas, factores = None, None
    if vigente is not None:
        modelo = registro.cargar_modelo(rutas.models / vigente["archivo"])
        resultado = evaluar_vigente(modelo, _dataset(rutas, fecha), params, costos)
        if resultado is not None:
            metricas, factores = resultado
    evaluacion["vigente"] = {"info": vigente, "metricas": metricas, "factores": factores}
    registro.guardar_evaluacion(rutas.models, fecha, evaluacion)
    return evaluacion["vigente"]


def decidir(fecha, rutas: Rutas | None = None) -> dict:
    """Aplica el criterio de reemplazo. No modifica el registro (eso lo hace ``aplicar``)."""
    rutas = _rutas(rutas)
    params = cargar_parametros(rutas)
    evaluacion = registro.leer_evaluacion(rutas.models, fecha)
    decision = compuerta.decidir(
        evaluacion["candidato"],
        evaluacion["baseline"],
        (evaluacion.get("vigente") or {}).get("metricas"),
        metrica=params.metrica_reemplazo,
        mejora_minima_pct=params.mejora_minima_pct,
    )
    return decision.como_dict()


def aplicar(fecha, decision: dict, rutas: Rutas | None = None) -> dict:
    """Registra la decisión y el modelo vigente que resulta para esta semana."""
    rutas = _rutas(rutas)
    txt = f"{_f(fecha):%Y-%m-%d}"
    previo = registro.vigente_antes_de(rutas.models, fecha)
    if decision["accion"] == compuerta.PROMOVER:
        vigente = {"modelo": f"boosting_{txt}", "archivo": f"candidatos/boosting_{txt}.pkl",
                   "tipo": "boosting", "desde": txt}
    elif decision["accion"] == compuerta.BASELINE:
        vigente = {"modelo": f"baseline_{txt}", "archivo": f"candidatos/baseline_{txt}.pkl",
                   "tipo": "baseline", "desde": txt}
    elif previo is not None:
        vigente = previo
    else:  # pragma: no cover - la compuerta nunca conserva cuando no hay vigente
        raise RuntimeError("No hay modelo vigente que conservar")
    registro.guardar_decision(rutas.models, fecha, {
        "corte": txt, "decision": decision, "vigente_anterior": previo, "vigente": vigente})
    logger.info("%s: %s -> vigente %s", txt, decision["accion"], vigente["modelo"])
    return vigente


def publicar(fecha, rutas: Rutas | None = None) -> dict:
    """Pronóstico del horizonte y pedido sugerido con el modelo vigente de la semana."""
    rutas = _rutas(rutas)
    costos = cargar_costos(rutas)
    params = cargar_parametros(rutas, costos.horizonte)
    txt = f"{_f(fecha):%Y-%m-%d}"
    decision = registro.leer_decision(rutas.models, fecha)
    if decision is None:
        raise RuntimeError(f"No hay decisión registrada para el corte {txt}")
    vigente = registro.cargar_modelo(rutas.models / decision["vigente"]["archivo"])
    baseline = registro.cargar_modelo(registro.ruta_candidato(rutas.models, fecha, "baseline"))
    # Todos los factores del pedido salen de la validación de esta semana: el candidato y el
    # baseline se calibraron al entrenar; si se conserva el vigente, se usa su recalibración.
    factores = vigente.factores
    if decision["decision"]["accion"] == compuerta.CONSERVAR:
        recalibrados = (registro.leer_evaluacion(rutas.models, fecha).get("vigente") or {}).get(
            "factores")
        factores = recalibrados or factores

    _, _, futuro = dividir(_dataset(rutas, fecha), params)
    futuro = futuro.copy()
    salida = futuro[["corte", "date", "store_nbr", "family"]].copy()
    salida["venta_esperada"] = vigente.predecir(futuro).round(3)
    salida["pedido_sugerido"] = calcular_pedido(futuro["family"], salida["venta_esperada"],
                                                factores)
    salida["venta_baseline"] = baseline.predecir(futuro).round(3)
    salida["pedido_baseline"] = calcular_pedido(futuro["family"], salida["venta_baseline"],
                                                baseline.factores)
    salida["modelo"] = decision["vigente"]["modelo"]
    salida = salida.sort_values(["date", "store_nbr", "family"]).reset_index(drop=True)
    ruta = escribir_parquet(salida, seguimiento.ruta_pronostico(rutas, fecha))

    semanal = pedido_semanal(salida, _f(fecha), costos.dias_pedido)
    ruta_semanal = escribir_csv(semanal, rutas.forecasts / f"pedido_semanal_{txt}.csv")
    return {
        "pronostico": str(ruta),
        "pedido_semanal": str(ruta_semanal),
        "modelo": decision["vigente"]["modelo"],
        "filas": int(len(salida)),
        "unidades_semana": int(semanal["pedido_sugerido"].sum()),
    }


def pronostico_publicado(fecha, rutas: Rutas | None = None) -> bool:
    return seguimiento.ruta_pronostico(_rutas(rutas), fecha).exists()


# --------------------------------------------------------------------------- seguimiento
def lunes_anterior(fecha) -> pd.Timestamp:
    """El lunes de la semana anterior a ``fecha`` (corte del pronóstico que debía cubrirla)."""
    fecha = _f(fecha)
    return fecha - pd.Timedelta(days=fecha.dayofweek + 7)


def pronostico_previo_listo(fecha, rutas: Rutas | None = None) -> bool:
    """Para evaluar la semana que termina en ``fecha`` hace falta el pronóstico del lunes
    anterior (si correspondía publicarlo dentro del periodo de operación)."""
    rutas = _rutas(rutas)
    previo = lunes_anterior(fecha)
    if previo < cargar_operacion(rutas).inicio:
        return True
    return pronostico_publicado(previo, rutas)


def seguir(fecha, rutas: Rutas | None = None) -> dict:
    rutas = _rutas(rutas)
    semana = seguimiento.evaluar_semana(rutas, _f(fecha), cargar_costos(rutas))
    general = seguimiento.consolidar(rutas)
    return {"filas_semana": int(len(semana)), **general}


# --------------------------------------------------------------------------- estado
def estado(rutas: Rutas | None = None) -> dict:
    """Resumen de avance de la operación (para revisar el producto sin abrir los archivos)."""
    rutas = _rutas(rutas)
    operacion = cargar_operacion(rutas)
    lunes = operacion.lunes()
    despues_del_fin = operacion.fin_operacion + pd.Timedelta(days=1)
    vigente = registro.vigente_antes_de(rutas.models, despues_del_fin)
    general = rutas.reports / "resumen_general.json"
    return {
        "periodo": [f"{operacion.inicio:%Y-%m-%d}", f"{operacion.fin_operacion:%Y-%m-%d}"],
        "carga_inicial": (rutas.raw / "_carga_inicial.json").exists(),
        "dias_ingeridos": len(operacion.dias())
        - len(proceso.dias_sin_ingerir(rutas, operacion.inicio, operacion.fin_operacion)),
        "dias_operacion": len(operacion.dias()),
        "cortes_semanales": len(lunes),
        "variables": len(list(rutas.processed.glob("features_*.parquet"))),
        "decisiones": len(list((rutas.models / "decisiones").glob("*.json"))),
        "pronosticos": len(list(rutas.forecasts.glob("pronostico_*.parquet"))),
        "seguimientos": len(list((rutas.reports / "seguimiento").glob("*.parquet"))),
        "modelo_vigente": vigente["modelo"] if vigente else None,
        "resumen_seguimiento": json.loads(general.read_text("utf-8")) if general.exists() else None,
    }


# --------------------------------------------------------------------------- todo junto
def semana(fecha, rutas: Rutas | None = None) -> dict:
    """Preparación, pronóstico y seguimiento de un lunes, en el orden de los DAGs."""
    rutas = _rutas(rutas)
    preparar_features(fecha, rutas)
    entrenar(fecha, rutas)
    evaluar_modelo_vigente(fecha, rutas)
    decision = decidir(fecha, rutas)
    vigente = aplicar(fecha, decision, rutas)
    publicado = publicar(fecha, rutas)
    seguido = seguir(fecha, rutas)
    return {"decision": decision, "vigente": vigente, "publicado": publicado,
            "seguimiento": seguido}


def operar(hasta, rutas: Rutas | None = None) -> dict:
    """Ejecuta toda la operación desde el inicio de la bandeja hasta ``hasta``, en orden.

    Hace lo mismo que los DAGs, pero en un solo proceso: lo usan DVC y las pruebas.
    """
    rutas = _rutas(rutas)
    operacion = cargar_operacion(rutas)
    hasta = min(_f(hasta), operacion.fin_operacion)
    carga_inicial(rutas)
    for dia in pd.date_range(operacion.inicio, hasta, freq="D"):
        proceso.ingerir_dia(rutas, operacion.fuentes_bandeja, dia)
        if dia.dayofweek == 0:
            resultado = semana(dia, rutas)
            logger.info("%s %s", f"{dia:%Y-%m-%d}", resultado["decision"]["motivo"])
    return seguimiento.consolidar(rutas)
