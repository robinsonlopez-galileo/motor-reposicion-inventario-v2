"""Operación completa sobre los datos sintéticos: lo mismo que hacen los DAGs, en orden."""
import hashlib
import json

import pandas as pd
import pytest
from conftest import preparar_proyecto

from motor_reposicion import cli, pipeline
from motor_reposicion.modelo import compuerta, registro

LUNES = ["2016-02-01", "2016-02-08", "2016-02-15", "2016-02-22"]


@pytest.fixture(scope="module")
def operado(tmp_path_factory):
    """La operación se ejecuta una sola vez para todas las pruebas del módulo."""
    with pytest.MonkeyPatch.context() as mp:
        rutas = preparar_proyecto(tmp_path_factory.mktemp("operacion"), mp)
        resumen = pipeline.operar("2016-02-22", rutas)
        yield rutas, resumen


def _md5(ruta):
    return hashlib.md5(ruta.read_bytes()).hexdigest()


def test_publica_pronostico_y_pedido_cada_lunes(operado):
    rutas, _ = operado
    for lunes in LUNES:
        pron = pd.read_parquet(rutas.forecasts / f"pronostico_{lunes}.parquet")
        assert len(pron) == 16 * 3 * 4
        assert pron["date"].min() == pd.Timestamp(lunes) + pd.Timedelta(days=1)
        assert (pron["pedido_sugerido"] >= 0).all()
        assert pron["pedido_sugerido"].dtype == "int64"
        assert pron["venta_esperada"].notna().all()
        semanal = pd.read_csv(rutas.forecasts / f"pedido_semanal_{lunes}.csv")
        assert len(semanal) == 12
        assert semanal["pedido_sugerido"].sum() > 0


def test_cada_semana_registra_una_decision(operado):
    rutas, _ = operado
    historial = registro.historial_decisiones(rutas.models)
    assert historial["corte"].tolist() == LUNES
    acciones = set(historial["accion"])
    assert acciones <= {compuerta.PROMOVER, compuerta.CONSERVAR, compuerta.BASELINE}
    primera = registro.leer_decision(rutas.models, LUNES[0])
    assert primera["vigente_anterior"] is None
    evaluacion = registro.leer_evaluacion(rutas.models, LUNES[1])
    assert evaluacion["vigente"]["metricas"] is not None
    assert set(evaluacion["vigente"]["factores"]) >= {"__global__"}
    assert {"MAE", "RMSE", "WAPE", "costo_total"} <= set(evaluacion["candidato"])


def test_seguimiento_compara_con_ventas_reales(operado):
    rutas, resumen = operado
    detalle = pd.read_csv(rutas.reports / "historial_desempeno.csv")
    assert set(detalle["corte"]) == set(LUNES[:3])
    assert detalle["horizonte_dia"].between(1, 16).all()
    assert resumen["pronosticos_evaluados"] == 3
    general = json.loads((rutas.reports / "resumen_general.json").read_text("utf-8"))
    assert general["costo_total_motor"] > 0


def test_reejecutar_una_semana_es_idempotente(operado):
    rutas, _ = operado
    archivo = rutas.forecasts / "pronostico_2016-02-15.parquet"
    antes = _md5(archivo)
    decision = registro.leer_decision(rutas.models, "2016-02-15")
    pipeline.semana("2016-02-15", rutas)
    assert _md5(archivo) == antes
    assert registro.leer_decision(rutas.models, "2016-02-15") == decision


def test_estado_resume_el_avance(operado):
    rutas, _ = operado
    resumen = pipeline.estado(rutas)
    assert resumen["carga_inicial"] is True
    assert resumen["dias_ingeridos"] == 22  # del 2016-02-01 al 2016-02-22
    assert resumen["pronosticos"] == resumen["decisiones"] == 4
    assert resumen["modelo_vigente"]


def test_sensores_de_seguimiento(operado):
    rutas, _ = operado
    assert pipeline.ingesta_lista("2016-02-22", rutas)
    assert not pipeline.ingesta_lista("2016-02-23", rutas)
    assert pipeline.features_listas("2016-02-22", rutas)
    assert pipeline.lunes_anterior("2016-02-15") == pd.Timestamp("2016-02-08")
    assert pipeline.pronostico_previo_listo("2016-02-01", rutas)  # no había pronóstico previo
    assert pipeline.pronostico_previo_listo("2016-02-29", rutas)
    assert not pipeline.pronostico_previo_listo("2016-03-07", rutas)


def test_reproducir_un_pronostico_pasado(rutas, tmp_path):
    salida = tmp_path / "reproduccion"
    metricas = cli.reproducir("2016-02-08", salida)
    assert metricas["corte"] == "2016-02-08"
    primera = _md5(salida / "pronostico.parquet")
    cli.reproducir("2016-02-08", salida)
    assert _md5(salida / "pronostico.parquet") == primera
    with pytest.raises(SystemExit):
        cli.reproducir("2016-02-09", salida)
