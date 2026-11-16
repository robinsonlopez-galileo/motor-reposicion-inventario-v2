import pandas as pd
import pytest

from motor_reposicion.ingesta.validadores import ErrorEstructura, validar_estructura, validar_filas

TIENDAS = {1, 2, 3}
FAMILIAS = {"BEVERAGES", "DAIRY"}


def _ventas(**cambios) -> pd.DataFrame:
    base = {"id": ["1"], "date": ["2016-02-01"], "store_nbr": ["1"], "family": ["BEVERAGES"],
            "sales": ["10.0"], "onpromotion": ["0"]}
    base.update(cambios)
    return pd.DataFrame(base)


def test_estructura_correcta():
    assert validar_estructura(_ventas(), "ventas") == []


def test_columnas_faltantes_y_archivo_vacio():
    errores = validar_estructura(pd.DataFrame({"date": []}), "ventas")
    assert any("Columnas faltantes" in e for e in errores)
    assert any("no tiene filas" in e for e in errores)
    with pytest.raises(ErrorEstructura):
        validar_filas(pd.DataFrame({"date": ["2016-02-01"]}), "ventas", TIENDAS, FAMILIAS)


@pytest.mark.parametrize(
    ("cambio", "motivo"),
    [
        ({"sales": ["-5"]}, "venta negativa"),
        ({"sales": ["abc"]}, "venta no numérica"),
        ({"store_nbr": ["99"]}, "tienda desconocida"),
        ({"store_nbr": ["uno"]}, "tienda no numérica"),
        ({"family": ["JUGUETES"]}, "familia desconocida"),
        ({"date": ["2016-13-45"]}, "fecha inválida"),
        ({"onpromotion": ["-1"]}, "promoción inválida"),
    ],
)
def test_filas_imposibles_se_rechazan_con_motivo(cambio, motivo):
    resultado = validar_filas(_ventas(**cambio), "ventas", TIENDAS, FAMILIAS)
    assert resultado.validas.empty
    assert resultado.rechazadas["motivo"].tolist() == [motivo]


def test_normaliza_familia_y_conserva_la_ultima_repetida():
    df = pd.concat([_ventas(family=[" beverages "], sales=["5"]), _ventas(sales=["7"])])
    resultado = validar_filas(df, "ventas", TIENDAS, FAMILIAS)
    assert len(resultado.validas) == 1
    assert resultado.validas["sales"].iloc[0] == 7
    assert resultado.duplicadas == 1
    assert resultado.resumen()["avisos"]


def test_petroleo_sin_precio_es_valido():
    df = pd.DataFrame({"date": ["2016-02-01"], "dcoilwtico": [None]})
    resultado = validar_filas(df, "oil", TIENDAS)
    assert len(resultado.validas) == 1
    assert resultado.validas["dcoilwtico"].isna().all()


def test_transacciones_negativas_se_rechazan():
    df = pd.DataFrame({"date": ["2016-02-01", "2016-02-01"], "store_nbr": ["1", "2"],
                       "transactions": ["900", "-3"]})
    resultado = validar_filas(df, "transactions", TIENDAS)
    assert resultado.validas["store_nbr"].tolist() == [1]
    assert resultado.rechazadas["motivo"].tolist() == ["transacciones inválidas"]
