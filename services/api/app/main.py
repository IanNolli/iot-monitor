"""API FastAPI da solução Smart Home AIoT."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from . import consumidores, db, estado, ia, rotas, seguranca

logging.basicConfig(level=logging.INFO, format="%(asctime)s [api] %(name)s: %(message)s")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    for tentativa in range(30):
        try:
            await db.iniciar()
            break
        except Exception as erro:
            logging.warning("PostgreSQL indisponível (%s); nova tentativa em 2 s", erro)
            await asyncio.sleep(2)
    await consumidores.iniciar()
    yield
    await consumidores.encerrar()
    await db.encerrar()


app = FastAPI(
    title="Smart Home AIoT — API",
    description="API REST e WebSocket do monitoramento residencial com manutenção preditiva do compressor da geladeira.",
    version="2.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
    lifespan=ciclo_de_vida,
)
app.include_router(rotas.rotas)
app.include_router(ia.rotas)


@app.get("/api/saude", tags=["infraestrutura"], summary="Healthcheck")
async def saude():
    await db.pool.fetchval("SELECT 1")
    return {"status": "ok", "rabbitmq": consumidores.exchange is not None, "websockets": len(estado.conexoes.ativas)}


@app.websocket("/ws")
async def websocket(ws: WebSocket, ticket: str = ""):
    # O JWT não vai na URL: o navegador pede um ticket curto (POST /api/ws/ticket) e usa aqui uma vez
    usuario = seguranca.consumir_ticket(ticket)
    if usuario is None:
        await ws.close(code=4401, reason="ticket inválido ou expirado")
        return
    await ws.accept()
    await estado.conexoes.entrar(ws)
    try:
        while True:
            await ws.receive_text()  # o cliente só mantém a conexão
    except WebSocketDisconnect:
        pass
    finally:
        estado.conexoes.sair(ws)
