# Airflow 3.3.2 (Python 3.12) con el paquete del motor instalado. Los DAGs, el código y la
# configuración viajan dentro de la imagen: lo que corre es exactamente lo del tag entregado.
FROM apache/airflow:3.3.2-python3.12

# Carpetas del motor, del usuario airflow (grupo root, como pide la imagen oficial para poder
# correr con cualquier AIRFLOW_UID). /opt/motor/data se monta como volumen con estos permisos.
USER root
RUN mkdir -p /opt/motor/data /opt/motor/datos/kaggle \
    && chown -R airflow:root /opt/motor && chmod -R g+rwX /opt/motor
USER airflow

COPY docker/constraints-airflow-3.3.2-python3.12.txt /tmp/constraints.txt
COPY --chown=airflow:root pyproject.toml /opt/motor/pyproject.toml
COPY --chown=airflow:root src/ /opt/motor/src/
# pandas, numpy, scikit-learn, pyarrow y PyYAML están fijados en pyproject.toml con las mismas
# versiones de las restricciones oficiales de Airflow 3.3.2: no se altera ninguna dependencia.
RUN pip install --no-cache-dir "apache-airflow==3.3.2" "apache-airflow-providers-fab==3.9.0" \
        /opt/motor --constraint /tmp/constraints.txt \
    && python -c "import motor_reposicion, sklearn, pyarrow; print('motor', motor_reposicion.__version__)"

COPY --chown=airflow:root config/ /opt/motor/config/
COPY --chown=airflow:root dags/ /opt/airflow/dags/

ENV MOTOR_DATA_DIR=/opt/motor/data \
    MOTOR_KAGGLE_DIR=/opt/motor/datos/kaggle \
    MOTOR_CONFIG_DIR=/opt/motor/config \
    OMP_WAIT_POLICY=PASSIVE
