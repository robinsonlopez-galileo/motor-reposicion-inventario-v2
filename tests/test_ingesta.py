import json

import pandas as pd
import pytest

from motor_reposicion.carga_inicial import construir_carga_inicial
from motor_reposicion.configuracion import cargar_operacion
from motor_reposicion.ingesta import almacen
from motor_reposicion.ingesta.lector import archivos_del_dia
from motor_reposicion.ingesta.proceso import (
    ErrorEstructura,
    dias_sin_ingerir,
    ingerir_dia,
    ruta_marcador,
    validar_entrega,
)


@pytest.fixture
def cargado(rutas):
    operacion = cargar_operacion(rutas)
    construir_carga_inicial(rutas, operacion)
    return rutas, operacion


def test_ingesta_de_un_dia_y_marcador(cargado):
    rutas, operacion = cargado
    marcador = ingerir_dia(rutas, operacion.fuentes_bandeja, "2016-02-01")
    estados = {r["fuente"]: r["estado"] for r in marcador["fuentes"]}
    assert estados == {"ventas": "consolidado", "oil": "consolidado", "transactions": "consolidado"}
    assert ruta_marcador(rutas, "2016-02-01").exists()
    ventas = almacen.leer_fuente(rutas.raw, "ventas")
    assert ventas["date"].max() == pd.Timestamp("2016-02-01")
    assert dias_sin_ingerir(rutas, operacion.inicio, pd.Timestamp("2016-02-02")) == ["2016-02-02"]


def test_dia_sin_archivo_no_es_error(cargado):
    rutas, operacion = cargado
    marcador = ingerir_dia(rutas, operacion.fuentes_bandeja, "2016-02-06")  # sábado
    oil = next(r for r in marcador["fuentes"] if r["fuente"] == "oil")
    assert oil["estado"] == "sin_archivo"


def test_reejecutar_un_dia_da_el_mismo_resultado(cargado):
    rutas, operacion = cargado
    ingerir_dia(rutas, operacion.fuentes_bandeja, "2016-02-01")
    antes = almacen.leer_fuente(rutas.raw, "ventas")
    ingerir_dia(rutas, operacion.fuentes_bandeja, "2016-02-01")
    pd.testing.assert_frame_equal(antes, almacen.leer_fuente(rutas.raw, "ventas"))


def test_filas_invalidas_se_descartan_y_registran(cargado):
    rutas, operacion = cargado
    ruta = rutas.inbox / "ventas" / "ventas_2016-02-02.csv"
    df = pd.read_csv(ruta)
    df.loc[0, "sales"] = -4
    df.to_csv(ruta, index=False)
    resultado = validar_entrega(rutas, "ventas", "2016-02-02")
    assert resultado["filas_rechazadas"] == 1
    assert resultado["motivos_rechazo"] == {"venta negativa": 1}
    rechazos = pd.read_csv(rutas.control / "rechazos" / "ventas_2016-02-02.csv")
    assert rechazos["motivo"].tolist() == ["venta negativa"]


def test_archivo_sin_columnas_hace_fallar_la_tarea(cargado):
    rutas, operacion = cargado
    ruta = rutas.inbox / "ventas" / "ventas_2016-02-03.csv"
    pd.read_csv(ruta).drop(columns=["sales"]).to_csv(ruta, index=False)
    with pytest.raises(ErrorEstructura, match="sales"):
        ingerir_dia(rutas, operacion.fuentes_bandeja, "2016-02-03")
    assert not ruta_marcador(rutas, "2016-02-03").exists()


def test_correccion_reemplaza_el_dato_anterior_desde_su_entrega(cargado):
    rutas, operacion = cargado
    for dia in ("2016-02-01", "2016-02-02"):
        ingerir_dia(rutas, operacion.fuentes_bandeja, dia)
    correccion = pd.DataFrame({"id": [0], "date": ["2016-02-01"], "store_nbr": [1],
                               "family": ["DAIRY"], "sales": [999.0], "onpromotion": [0]})
    correccion.to_csv(rutas.inbox / "ventas" / "ventas_2016-02-03_correccion.csv", index=False)
    assert [r.name for r in archivos_del_dia(rutas.inbox, "ventas", "2016-02-03")] == [
        "ventas_2016-02-03.csv", "ventas_2016-02-03_correccion.csv"]
    ingerir_dia(rutas, operacion.fuentes_bandeja, "2016-02-03")

    def valor(hasta):
        df = almacen.leer_fuente(rutas.raw, "ventas", hasta=hasta)
        fila = df[(df["date"] == "2016-02-01") & (df["store_nbr"] == 1) & (df["family"] == "DAIRY")]
        return float(fila["sales"].iloc[0])

    assert valor(pd.Timestamp("2016-02-03")) == 999.0
    # Al cierre del 2 de febrero la corrección todavía no había llegado: sin información futura.
    assert valor(pd.Timestamp("2016-02-02")) != 999.0


def test_dias_sin_ingerir_considera_todo_el_rango(cargado):
    rutas, operacion = cargado
    ingerir_dia(rutas, operacion.fuentes_bandeja, "2016-02-02")
    assert dias_sin_ingerir(rutas, operacion.inicio, pd.Timestamp("2016-02-02")) == ["2016-02-01"]
    ingerir_dia(rutas, operacion.fuentes_bandeja, "2016-02-01")
    assert dias_sin_ingerir(rutas, operacion.inicio, pd.Timestamp("2016-02-02")) == []
    marcador = json.loads(ruta_marcador(rutas, "2016-02-01").read_text("utf-8"))
    assert marcador["fecha"] == "2016-02-01"
