FROM python:3.12-slim
RUN useradd --uid 10001 --create-home app && mkdir -p /modelos /dados && chown app:app /modelos /dados
WORKDIR /app
COPY lab/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common /opt/common
RUN pip install --no-cache-dir /opt/common
COPY lab/*.py ./
USER app
HEALTHCHECK --interval=10s --timeout=5s --retries=5 CMD ["python", "-m", "aiot_common.saude"]
CMD ["python", "-u", "lab.py"]
