"""Cria a topologia do RabbitMQ pela API de gerenciamento e termina.

- vhost "aiot"
- um usuário por serviço, só com as permissões de que ele precisa (sem o usuário guest)
- exchange topic "aiot.eventos" e exchange de mensagens mortas "aiot.dlx" -> fila "aiot.dlq"
- filas de cada consumidor e as ligações (bindings) por routing key

Routing keys:  telemetria.<zona>.<tipo>.<id>   comando.<id>   previsao.<id>   alerta.<id>
               job.lab   job.treino   progresso.<job>   modelo.atualizado
"""

import os
import sys
import time
from urllib.parse import quote

import httpx

BASE = "http://rabbitmq:15672/api"
VHOST = "aiot"
V = quote(VHOST, safe="")
AUTH = ("admin", os.environ["RABBITMQ_SENHA_ADMIN"])

# usuário: (configure, write, read, tags)
USUARIOS = {
    "gateway": ("^$", r"^aiot\.(eventos|dlx)$", r"^q\.comandos$", ""),
    "gravador": ("^$", "^$", r"^q\.gravador$", ""),
    "inferencia": ("^$", r"^aiot\.eventos$", r"^q\.inferencia$", ""),
    "lab": ("^$", r"^aiot\.eventos$", r"^q\.jobs\..+$", ""),
    "api": ("^$", r"^aiot\.eventos$", r"^(q\.websocket|q\.regras|aiot\.dlq)$", "monitoring"),
}

COM_DLQ = {"x-dead-letter-exchange": "aiot.dlx"}

# fila: (argumentos, [routing keys])
FILAS = {
    "q.gravador": (COM_DLQ, ["telemetria.#", "previsao.#"]),
    "q.inferencia": (COM_DLQ, ["telemetria.*.equipamento.*", "modelo.atualizado"]),
    "q.regras": (COM_DLQ, ["telemetria.*.sensor.*", "telemetria.*.atuador.*", "alerta.#", "progresso.#", "modelo.atualizado"]),
    "q.comandos": (COM_DLQ, ["comando.#"]),
    "q.jobs.lab": (COM_DLQ, ["job.lab"]),
    "q.jobs.treino": (COM_DLQ, ["job.treino"]),
    # Entrega ao vivo para o WebSocket: só interessa o dado recente, então descarta o mais antigo
    "q.websocket": ({"x-max-length": 5000, "x-overflow": "drop-head"},
                    ["telemetria.#", "previsao.#", "alerta.#", "progresso.#", "modelo.atualizado", "comando.#"]),
}


def put(cliente: httpx.Client, caminho: str, corpo: dict) -> None:
    r = cliente.put(f"{BASE}{caminho}", json=corpo)
    if r.status_code >= 400:
        sys.exit(f"Falha em PUT {caminho}: {r.status_code} {r.text}")


def main() -> None:
    with httpx.Client(auth=AUTH, timeout=10) as cliente:
        for _ in range(60):
            try:
                if cliente.get(f"{BASE}/overview").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(2)
        else:
            sys.exit("RabbitMQ não respondeu")

        put(cliente, f"/vhosts/{V}", {"description": "Barramento interno AIoT"})
        put(cliente, f"/permissions/{V}/admin", {"configure": ".*", "write": ".*", "read": ".*"})

        for usuario, (conf, escrita, leitura, tags) in USUARIOS.items():
            senha = os.environ[f"RABBIT_SENHA_{usuario.upper()}"]
            put(cliente, f"/users/{usuario}", {"password": senha, "tags": tags})
            put(cliente, f"/permissions/{V}/{usuario}", {"configure": conf, "write": escrita, "read": leitura})

        put(cliente, f"/exchanges/{V}/aiot.eventos", {"type": "topic", "durable": True})
        put(cliente, f"/exchanges/{V}/aiot.dlx", {"type": "fanout", "durable": True})
        put(cliente, f"/queues/{V}/aiot.dlq", {"durable": True, "arguments": {}})
        cliente.post(f"{BASE}/bindings/{V}/e/aiot.dlx/q/aiot.dlq", json={"routing_key": ""}).raise_for_status()

        for fila, (argumentos, chaves) in FILAS.items():
            put(cliente, f"/queues/{V}/{fila}", {"durable": True, "arguments": argumentos})
            for chave in chaves:
                cliente.post(f"{BASE}/bindings/{V}/e/aiot.eventos/q/{fila}", json={"routing_key": chave}).raise_for_status()

    print("Topologia do RabbitMQ configurada.")


if __name__ == "__main__":
    main()
