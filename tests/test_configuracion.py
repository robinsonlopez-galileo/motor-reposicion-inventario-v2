import pandas as pd
import pytest
import yaml

from motor_reposicion.configuracion import (
    cargar_costos,
    cargar_operacion,
    cargar_parametros,
    rutas_desde_entorno,
)


def test_configuracion_del_repositorio_es_valida():
    rutas = rutas_desde_entorno()
    costos = cargar_costos(rutas)
    params = cargar_parametros(rutas)
    operacion = cargar_operacion(rutas)
    assert costos.cuantil_optimo == pytest.approx(0.75)
    assert min(params.lags) >= costos.horizonte
    assert operacion.inicio == operacion.corte_historico + pd.Timedelta(days=1)
    assert all(d.dayofweek == 0 for d in operacion.lunes())


def test_rezagos_menores_al_horizonte_se_rechazan(rutas):
    ruta = rutas.config / "model_params.yaml"
    cfg = yaml.safe_load(ruta.read_text("utf-8"))
    cfg["features"]["lags"] = [7, 28]
    ruta.write_text(yaml.safe_dump(cfg), "utf-8")
    with pytest.raises(ValueError, match="horizonte"):
        cargar_parametros(rutas)


def test_periodo_se_puede_cambiar_con_variables_de_entorno(rutas, monkeypatch):
    monkeypatch.setenv("CORTE_HISTORICO", "2016-02-14")
    monkeypatch.setenv("FIN_OPERACION", "2016-03-01")
    operacion = cargar_operacion(rutas)
    assert operacion.inicio == pd.Timestamp("2016-02-15")
    assert len(operacion.dias()) == 16


def test_fin_anterior_al_corte_es_un_error(rutas, monkeypatch):
    monkeypatch.setenv("FIN_OPERACION", "2015-01-01")
    with pytest.raises(ValueError, match="posterior"):
        cargar_operacion(rutas)
