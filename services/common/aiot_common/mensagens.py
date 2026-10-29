"""Formato único das mensagens que trafegam no RabbitMQ.

Toda mensagem é um JSON com:
    id           identificador único (uuid4)
    instante     data/hora ISO 8601 em UTC
    tipo         telemetria | comando | previsao | alerta | job | progresso | modelo
    dispositivo  id do dispositivo (ou null quando não se aplica)
    conteudo     objeto com os dados
"""

import json
import uuid
from datetime import datetime, timezone

EXCHANGE = "aiot.eventos"
EXCHANGE_DLX = "aiot.dlx"
FILA_DLQ = "aiot.dlq"


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def criar(tipo: str, conteudo: dict, dispositivo: str | None = None) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "instante": agora_iso(),
        "tipo": tipo,
        "dispositivo": dispositivo,
        "conteudo": conteudo,
    }


def codificar(mensagem: dict) -> bytes:
    return json.dumps(mensagem, ensure_ascii=False).encode("utf-8")


def decodificar(corpo: bytes) -> dict:
    """Valida o envelope. Lança ValueError se o formato não for o esperado."""
    mensagem = json.loads(corpo.decode("utf-8"))
    if not isinstance(mensagem, dict):
        raise ValueError("mensagem não é um objeto JSON")
    for campo in ("id", "instante", "tipo", "conteudo"):
        if campo not in mensagem:
            raise ValueError(f"campo obrigatório ausente: {campo}")
    if not isinstance(mensagem["conteudo"], dict):
        raise ValueError("conteudo deve ser um objeto")
    return mensagem
