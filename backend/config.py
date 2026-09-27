"""Leitura das variáveis de ambiente definidas no arquivo .env."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Carrega backend/.env independentemente da pasta de onde o app é iniciado
load_dotenv(Path(__file__).with_name(".env"))

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "casa/temperatura")

INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "")
INFLUX_ORG = os.getenv("INFLUX_ORG", "casa")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "iot")

API_PORT = int(os.getenv("API_PORT", "8000"))
