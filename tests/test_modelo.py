import numpy as np
import pandas as pd
import pytest

from motor_reposicion.configuracion import Costos
from motor_reposicion.modelo import compuerta, registro
from motor_reposicion.modelo.estimadores import ModeloBaseline
from motor_reposicion.modelo.metricas import metricas_tecnicas
from motor_reposicion.pedido import (
    calcular_pedido,
    calibrar_factores,
    costo_pedido,
    cuantil_ponderado,
    pedido_semanal,
)

COSTOS = Costos(quiebre=0.3, merma=0.1, horizonte=16, dias_pedido=7)


def test_metricas_tecnicas():
    m = metricas_tecnicas(np.array([10.0, 20.0, np.nan]), np.array([12.0, 18.0, 5.0]))
    assert m == {"MAE": 2.0, "RMSE": 2.0, "WAPE": pytest.approx(4 / 30, abs=1e-4), "n": 2}


def test_costo_pedido_asimetrico():
    costo = costo_pedido(np.array([100.0, 100.0]), np.array([110, 90]), COSTOS)
    assert costo["costo_merma"] == pytest.approx(1.0)  # 10 sobrantes * 0.10
    assert costo["costo_quiebre"] == pytest.approx(3.0)  # 10 faltantes * 0.30
    assert costo["costo_total"] == pytest.approx(4.0)


def test_cuantil_ponderado():
    assert cuantil_ponderado([1, 2, 3, 4], [1, 1, 1, 1], 0.75) == 3
    assert cuantil_ponderado([1, 2, 3, 4], [0, 0, 0, 1], 0.5) == 4
    with pytest.raises(ValueError):
        cuantil_ponderado([], [], 0.5)


def test_factores_minimizan_el_costo_de_validacion():
    rng = np.random.default_rng(0)
    pred = rng.uniform(5, 50, 2000)
    real = pred * rng.lognormal(0, 0.3, 2000)
    familias = pd.Series(["A"] * 2000)
    factores = calibrar_factores(familias, real, pred, COSTOS)
    k = factores["A"]
    costo = costo_pedido(real, calcular_pedido(familias, pred, factores), COSTOS)["costo_total"]
    for otro in (k * 0.9, k * 1.1):
        alternativo = costo_pedido(real, calcular_pedido(familias, pred, {"A": otro}), COSTOS)
        assert costo <= alternativo["costo_total"]
    assert COSTOS.limites_factor[0] <= k <= COSTOS.limites_factor[1]


def test_pedido_entero_y_no_negativo():
    pedido = calcular_pedido(pd.Series(["A", "B", "C", "D"]), np.array([-3.0, 0.05, 10.2, 3.0]),
                             {"A": 1.2, "__global__": 1.5})
    assert pedido.dtype == np.int64
    assert pedido.tolist() == [0, 0, 15, 5]  # 0.075 -> 0, 15.3 -> 15, 4.5 -> 5


def test_pedido_semanal_suma_los_siete_dias():
    fechas = pd.date_range("2016-02-09", periods=16)
    df = pd.DataFrame({"date": fechas, "store_nbr": 1, "family": "A",
                       "venta_esperada": 1.0, "pedido_sugerido": 2})
    semanal = pedido_semanal(df, pd.Timestamp("2016-02-08"), 7)
    assert semanal["pedido_sugerido"].tolist() == [14]
    assert semanal["semana_desde"].iloc[0] == "2016-02-09"
    assert semanal["semana_hasta"].iloc[0] == "2016-02-15"


@pytest.mark.parametrize(
    ("cand", "base", "vig", "accion"),
    [
        (90, 100, None, compuerta.PROMOVER),
        (110, 100, None, compuerta.BASELINE),
        (110, 100, 95, compuerta.CONSERVAR),
        (90, 100, 95, compuerta.PROMOVER),     # 5.3 % de mejora
        (94, 100, 95, compuerta.CONSERVAR),    # 1.05 % < 2 %
    ],
)
def test_compuerta(cand, base, vig, accion):
    decision = compuerta.decidir(
        {"costo_total": cand}, {"costo_total": base},
        {"costo_total": vig} if vig is not None else None,
        "costo_total", 2.0)
    assert decision.accion == accion
    assert decision.motivo


def test_baseline_usa_su_columna():
    df = pd.DataFrame({"baseline_misma_dia": [3.0, np.nan, -1.0], "date": pd.date_range(
        "2016-01-01", periods=3)})
    assert ModeloBaseline().ajustar(df).predecir(df).tolist() == [3.0, 0.0, 0.0]


def test_registro_vigente_no_depende_del_orden(tmp_path):
    def decision(corte, modelo):
        registro.guardar_decision(tmp_path, corte, {
            "corte": corte, "decision": {"accion": "x", "motivo": "y"},
            "vigente": {"modelo": modelo, "archivo": f"{modelo}.pkl", "tipo": "boosting",
                        "desde": corte}})

    decision("2016-02-15", "b")
    decision("2016-02-01", "a")
    assert registro.vigente_antes_de(tmp_path, "2016-02-01") is None
    assert registro.vigente_antes_de(tmp_path, "2016-02-08")["modelo"] == "a"
    assert registro.vigente_antes_de(tmp_path, "2016-02-15")["modelo"] == "a"
    assert registro.vigente_antes_de(tmp_path, "2016-02-22")["modelo"] == "b"
    assert registro.historial_decisiones(tmp_path)["vigente"].tolist() == ["a", "b"]


def test_registro_guarda_y_carga_modelos(tmp_path):
    modelo = ModeloBaseline(semanas=4, factores={"A": 1.3})
    ruta = registro.guardar_modelo(modelo, registro.ruta_candidato(tmp_path, "2016-02-01",
                                                                  "baseline"))
    assert ruta.name == "baseline_2016-02-01.pkl"
    assert registro.cargar_modelo(ruta) == modelo
