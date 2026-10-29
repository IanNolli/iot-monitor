"""Estado em memória da API: últimos valores, previsões e conexões WebSocket."""

import asyncio
import json
import time
from collections import deque

from fastapi import WebSocket

ultimas_leituras: dict[str, dict] = {}   # dispositivo -> última mensagem de telemetria
ultimas_previsoes: dict[str, dict] = {}  # dispositivo -> última previsão da IA
mensagens_recentes: deque = deque(maxlen=40)  # para a página Mensageria
ultima_telemetria_em: float = 0.0


class Conexoes:
    def __init__(self) -> None:
        self.ativas: set[WebSocket] = set()

    async def entrar(self, ws: WebSocket) -> None:
        self.ativas.add(ws)
        # estado inicial para a tela não começar vazia
        await ws.send_text(json.dumps({"tipo": "estado_inicial", "conteudo": {
            "leituras": ultimas_leituras, "previsoes": ultimas_previsoes, "ultima_telemetria_em": ultima_telemetria_em}}))

    def sair(self, ws: WebSocket) -> None:
        self.ativas.discard(ws)

    async def transmitir(self, texto: str) -> None:
        mortas = []
        for ws in list(self.ativas):
            try:
                await asyncio.wait_for(ws.send_text(texto), timeout=2)
            except Exception:
                mortas.append(ws)
        for ws in mortas:
            self.sair(ws)


conexoes = Conexoes()


def registrar_telemetria(m: dict) -> None:
    global ultima_telemetria_em
    ultimas_leituras[m["dispositivo"]] = m
    ultima_telemetria_em = time.time()
