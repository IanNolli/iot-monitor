FROM python:3.12-slim
RUN useradd --uid 10001 --create-home app && mkdir -p /modelos /dados && chown app:app /modelos /dados
WORKDIR /app
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common /opt/common
RUN pip install --no-cache-dir /opt/common
COPY api/app ./app
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --retries=10 --start-period=20s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/saude', timeout=4)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
