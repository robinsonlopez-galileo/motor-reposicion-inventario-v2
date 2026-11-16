"""Datos sintéticos con el formato de Kaggle (train, stores, oil, holidays_events, transactions).

Sirven para las pruebas automáticas y para la prueba integral de Docker en la CI, donde no están
los archivos reales de Kaggle. Uso: ``python -m motor_reposicion.sintetico <carpeta>``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

TIENDAS = [1, 2, 3]
FAMILIAS = ["BEVERAGES", "BREAD/BAKERY", "DAIRY", "PRODUCE"]
INICIO = "2015-06-01"
CORTE = "2016-01-31"  # domingo: la bandeja empieza el lunes 2016-02-01
FIN = "2016-03-15"


def escribir_kaggle(carpeta: Path, semilla: int = 7) -> Path:
    """Escribe train, stores, oil, holidays_events y transactions sintéticos."""
    rng = np.random.default_rng(semilla)
    carpeta.mkdir(parents=True, exist_ok=True)
    fechas = pd.date_range(INICIO, FIN, freq="D")
    filas = []
    ident = 0
    for fecha in fechas:
        for tienda in TIENDAS:
            for j, familia in enumerate(FAMILIAS):
                nivel = 20 + 10 * j + 5 * tienda
                semanal = 1.4 if fecha.dayofweek >= 5 else 1.0
                ventas = 0.0 if (fecha.month == 1 and fecha.day == 1) else float(
                    rng.poisson(nivel * semanal))
                filas.append((ident, f"{fecha:%Y-%m-%d}", tienda, familia, ventas,
                              int(rng.integers(0, 3))))
                ident += 1
    pd.DataFrame(filas, columns=["id", "date", "store_nbr", "family", "sales",
                                 "onpromotion"]).to_csv(carpeta / "train.csv", index=False)
    pd.DataFrame({
        "store_nbr": TIENDAS,
        "city": ["Quito", "Quito", "Guayaquil"],
        "state": ["Pichincha", "Pichincha", "Guayas"],
        "type": ["A", "D", "B"],
        "cluster": [13, 13, 6],
    }).to_csv(carpeta / "stores.csv", index=False)
    habiles = fechas[fechas.dayofweek < 5]
    pd.DataFrame({"date": habiles.strftime("%Y-%m-%d"),
                  "dcoilwtico": np.round(50 + rng.normal(0, 1, len(habiles)).cumsum(), 2)}
                 ).to_csv(carpeta / "oil.csv", index=False)
    pd.DataFrame([
        ("2016-01-01", "Holiday", "National", "Ecuador", "Primer dia del ano", "False"),
        ("2015-12-25", "Holiday", "National", "Ecuador", "Navidad", "False"),
        ("2016-02-08", "Holiday", "National", "Ecuador", "Carnaval", "False"),
        ("2016-02-09", "Holiday", "Local", "Quito", "Fiesta local", "False"),
        ("2016-03-01", "Event", "National", "Ecuador", "Evento", "False"),
    ], columns=["date", "type", "locale", "locale_name", "description", "transferred"]).to_csv(
        carpeta / "holidays_events.csv", index=False)
    trans = [(f"{f:%Y-%m-%d}", t, int(rng.integers(800, 1200))) for f in fechas for t in TIENDAS]
    pd.DataFrame(trans, columns=["date", "store_nbr", "transactions"]).to_csv(
        carpeta / "transactions.csv", index=False)
    return carpeta


if __name__ == "__main__":
    destino = escribir_kaggle(Path(sys.argv[1] if len(sys.argv) > 1 else "datos/kaggle"))
    print(f"Datos sintéticos escritos en {destino} (corte {CORTE}, fin {FIN})")
