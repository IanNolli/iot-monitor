FROM python:3.12-slim
RUN pip install --no-cache-dir httpx==0.28.1 && useradd --uid 10001 --create-home app
USER app
WORKDIR /app
COPY configurar.py .
CMD ["python", "configurar.py"]
