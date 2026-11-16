# datos/

Cree la carpeta `datos/kaggle/` y coloque ahí los archivos de la competencia **Store Sales - Time Series Forecasting** de Kaggle:
https://www.kaggle.com/competitions/store-sales-time-series-forecasting/data

Sirven los CSV sueltos (`train.csv`, `stores.csv`, `oil.csv`, `holidays_events.csv`,
`transactions.csv`) o el ZIP tal como lo descarga Kaggle.
DVC rastrea esa carpeta completa (`datos/kaggle.dvc`). Los demás archivos de la competencia
(`test.csv`, `sample_submission.csv`) no se usan. Estos archivos no se suben a Git.
