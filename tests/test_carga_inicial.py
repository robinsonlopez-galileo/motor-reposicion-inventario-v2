import json
import zipfile

import pandas as pd
import pytest

from motor_reposicion.carga_inicial import ErrorCargaInicial, construir_carga_inicial
from motor_reposicion.configuracion import cargar_operacion
from motor_reposicion.ingesta import almacen


def test_construye_historico_y_bandeja(rutas):
    operacion = cargar_operacion(rutas)
    resumen = construir_carga_inicial(rutas, operacion)
    assert resumen["estado"] == "creada"
    ventas = almacen.leer_fuente(rutas.raw, "ventas")
    assert ventas["date"].max() == operacion.corte_historico
    archivos = sorted((rutas.inbox / "ventas").glob("*.csv"))
    assert archivos[0].name == "ventas_2016-02-01.csv"
    assert archivos[-1].name == "ventas_2016-03-15.csv"
    assert len(archivos) == len(operacion.dias())
    # El petróleo no cotiza en fin de semana: esos días no hay archivo en la bandeja.
    assert not (rutas.inbox / "oil" / "oil_2016-02-06.csv").exists()
    assert set(almacen.leer_catalogo(rutas.raw, "familias")["family"]) == {
        "BEVERAGES", "BREAD/BAKERY", "DAIRY", "PRODUCE"}


def test_es_idempotente(rutas):
    operacion = cargar_operacion(rutas)
    construir_carga_inicial(rutas, operacion)
    marca = (rutas.raw / "ventas" / "historico.parquet").stat().st_mtime_ns
    assert construir_carga_inicial(rutas, operacion)["estado"] == "existente"
    assert (rutas.raw / "ventas" / "historico.parquet").stat().st_mtime_ns == marca


def test_otro_periodo_sobre_la_misma_carga_es_un_error(rutas, monkeypatch):
    construir_carga_inicial(rutas, cargar_operacion(rutas))
    monkeypatch.setenv("CORTE_HISTORICO", "2016-02-14")
    with pytest.raises(ErrorCargaInicial, match="docker compose down -v"):
        construir_carga_inicial(rutas, cargar_operacion(rutas))


def test_acepta_el_zip_de_kaggle(rutas):
    with zipfile.ZipFile(rutas.kaggle / "store-sales-time-series-forecasting.zip", "w") as z:
        for archivo in list(rutas.kaggle.glob("*.csv")):
            z.write(archivo, archivo.name)
            archivo.unlink()
    resumen = construir_carga_inicial(rutas, cargar_operacion(rutas))
    assert resumen["fuentes"]["ventas"]["dias_bandeja"] == 44


def test_faltan_archivos(rutas):
    (rutas.kaggle / "oil.csv").unlink()
    with pytest.raises(ErrorCargaInicial, match="oil.csv"):
        construir_carga_inicial(rutas, cargar_operacion(rutas))


def test_reintento_tras_una_carga_interrumpida(rutas):
    (rutas.raw / "ventas").mkdir(parents=True)
    (rutas.raw / "ventas" / "basura.parquet").write_text("x")
    resumen = construir_carga_inicial(rutas, cargar_operacion(rutas))
    assert resumen["estado"] == "creada"
    assert not (rutas.raw / "ventas" / "basura.parquet").exists()
    marcador = json.loads((rutas.raw / "_carga_inicial.json").read_text("utf-8"))
    assert marcador["corte_historico"] == "2016-01-31"
    assert pd.Timestamp(marcador["fuentes"]["ventas"]["desde"]) == pd.Timestamp("2015-06-01")
