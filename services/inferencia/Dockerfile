FROM python:3.12-slim
RUN useradd --uid 10001 --create-home app && mkdir -p /modelos && chown app:app /modelos
WORKDIR /app
COPY inferencia/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common /opt/common
RUN pip install --no-cache-dir /opt/common
COPY inferencia/inferencia.py .
USER app
HEALTHCHECK --interval=10s --timeout=5s --retries=5 CMD ["python", "-m", "aiot_common.saude"]
CMD ["python", "-u", "inferencia.py"]
