import numpy as np
import pandas as pd
import pytest

from motor_reposicion.carga_inicial import construir_carga_inicial
from motor_reposicion.configuracion import cargar_costos, cargar_operacion, cargar_parametros
from motor_reposicion.features import (
    Fuentes,
    cargar_fuentes,
    columnas_modelo,
    construir_dataset,
)
from motor_reposicion.ingesta.proceso import ingerir_dia

CORTE = pd.Timestamp("2016-02-08")


@pytest.fixture
def entorno(rutas):
    operacion = cargar_operacion(rutas)
    construir_carga_inicial(rutas, operacion)
    for dia in pd.date_range(operacion.inicio, "2016-02-20"):
        ingerir_dia(rutas, operacion.fuentes_bandeja, dia)
    costos = cargar_costos(rutas)
    return rutas, costos, cargar_parametros(rutas, costos.horizonte)


def test_filas_del_horizonte(entorno):
    rutas, costos, params = entorno
    ds = construir_dataset(cargar_fuentes(rutas, CORTE), costos.horizonte, params)
    futuro = ds[ds["es_futuro"] == 1]
    assert futuro["date"].min() == CORTE + pd.Timedelta(days=1)
    assert futuro["date"].max() == CORTE + pd.Timedelta(days=costos.horizonte)
    assert futuro["sales"].isna().all()
    assert len(futuro) == costos.horizonte * 3 * 4
    assert set(columnas_modelo(params)) <= set(ds.columns)


def test_no_usa_informacion_posterior_al_corte(entorno):
    """Las variables no cambian si se alteran o agregan ventas posteriores al corte."""
    rutas, costos, params = entorno
    fuentes = cargar_fuentes(rutas, pd.Timestamp("2016-02-20"))
    alteradas = fuentes.ventas.copy()
    despues = alteradas["date"] > CORTE
    alteradas.loc[despues, "sales"] = alteradas.loc[despues, "sales"] * 100 + 7

    def con(ventas):
        return construir_dataset(
            Fuentes(CORTE, ventas, fuentes.oil, fuentes.transactions, fuentes.feriados,
                    fuentes.tiendas, fuentes.familias),
            costos.horizonte, params)

    a, b = con(fuentes.ventas), con(alteradas)
    columnas = columnas_modelo(params)
    pd.testing.assert_frame_equal(a[columnas], b[columnas])
    # Y coinciden con lo que se lee al cierre del corte.
    c = construir_dataset(cargar_fuentes(rutas, CORTE), costos.horizonte, params)
    pd.testing.assert_frame_equal(a[columnas], c[columnas])


def test_rezagos_y_baseline(entorno):
    rutas, costos, params = entorno
    fuentes = cargar_fuentes(rutas, CORTE)
    ds = construir_dataset(fuentes, costos.horizonte, params)
    serie = fuentes.ventas[(fuentes.ventas["store_nbr"] == 2)
                           & (fuentes.ventas["family"] == "DAIRY")].set_index("date")["sales"]
    fila = ds[(ds["store_nbr"] == 2) & (ds["family"] == "DAIRY")
              & (ds["date"] == CORTE + pd.Timedelta(days=5))].iloc[0]
    t = fila["date"]
    assert fila["lag_21"] == pytest.approx(serie[t - pd.Timedelta(days=21)])
    semanas = [serie[t - pd.Timedelta(days=7 * j)] for j in range(3, 3 + params.semanas_baseline)]
    assert fila["baseline_misma_dia"] == pytest.approx(np.mean(semanas), rel=1e-5)
    hasta = t - pd.Timedelta(days=costos.horizonte)
    ventana = serie[(serie.index > hasta - pd.Timedelta(days=7)) & (serie.index <= hasta)]
    assert fila["media_7"] == pytest.approx(ventana.mean(), rel=1e-5)


def test_calendario_y_tienda_cerrada(entorno):
    rutas, costos, params = entorno
    ds = construir_dataset(cargar_fuentes(rutas, CORTE), costos.horizonte, params)
    carnaval = ds[ds["date"] == "2016-02-08"]
    assert carnaval["feriado_nacional"].eq(1).all()
    local = ds[ds["date"] == "2016-02-09"].groupby("store_nbr")["feriado_local"].max()
    assert local.to_dict() == {1: 1, 2: 1, 3: 0}  # solo las tiendas de Quito
    anio_nuevo = ds[ds["date"] == "2016-01-01"]
    assert anio_nuevo["tienda_cerrada"].eq(1).all()
    assert ds.loc[ds["date"] == "2016-01-02", "tienda_cerrada"].eq(0).all()
