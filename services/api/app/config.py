import os

JWT_SEGREDO = os.environ["JWT_SEGREDO"]
JWT_HORAS = 8
POSTGRES_DSN = f"postgresql://aiot:{os.environ['POSTGRES_SENHA']}@postgres:5432/aiot"
INFLUX_URL = os.getenv("INFLUX_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.environ["INFLUX_TOKEN"]
INFLUX_ORG = "casa"
INFLUX_BUCKET = "iot"
RABBIT_MGMT = "http://rabbitmq:15672/api"
RABBIT_SENHA = os.environ["RABBIT_SENHA_API"]
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODELO = os.getenv("OLLAMA_MODELO", "llama3.2:3b")

USUARIOS_DEMO = {
    "administrador": ("Administrador", "administrador", os.environ["SENHA_ADMINISTRADOR"]),
    "operador": ("Operador", "operador", os.environ["SENHA_OPERADOR"]),
    "visualizador": ("Visualizador", "visualizador", os.environ["SENHA_VISUALIZADOR"]),
}

LOGIN_MAX_FALHAS = 5
LOGIN_BLOQUEIO_MIN = 5
