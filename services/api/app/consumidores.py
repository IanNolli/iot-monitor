"""Consumidores do RabbitMQ dentro da API.

q.websocket -> entrega ao vivo para o navegador (e caches de última leitura/previsão)
q.regras    -> regras de negócio (atuador automático) e persistência no PostgreSQL de
               alertas, progresso de jobs e versões de modelos
"""

import asyncio
import json
import logging
import time

import aio_pika
from aiot_common import mensagens, rabbit

from . import db, estado

log = logging.getLogger("api.consumidores")

exchange: aio_pika.abc.AbstractExchange | None = None
_conexao = None
_regras: list[dict] = []
_ultimo_comando_regra: dict[str, float] = {}


async def publicar(routing_key: str, mensagem: dict) -> None:
    await rabbit.publicar(exchange, routing_key, mensagem)


async def recarregar_regras() -> None:
    global _regras
    _regras = [dict(r) for r in await db.pool.fetch("SELECT * FROM regras WHERE ativa")]


async def _aplicar_regras(m: dict) -> None:
    """Liga acima de limite_liga, desliga abaixo de limite_desliga (histerese entre os dois)."""
    sensor = m["dispositivo"]
    valor = m["conteudo"].get("valor")
    if valor is None:
        return
    for regra in _regras:
        if regra["sensor_id"] != sensor:
            continue
        atuador = regra["atuador_id"]
        ligado = bool(estado.ultimas_leituras.get(atuador, {}).get("conteudo", {}).get("ligado"))
        desejado = True if valor > regra["limite_liga"] else False if valor < regra["limite_desliga"] else ligado
        if desejado == ligado or time.time() - _ultimo_comando_regra.get(atuador, 0) < 10:
            continue
        _ultimo_comando_regra[atuador] = time.time()
        conteudo = {"ligado": desejado, "origem": "regra", "regra": regra["nome"]}
        await publicar(f"comando.{atuador}", mensagens.criar("comando", conteudo, atuador))
        await db.auditar("regra-automatica", "comando", {"dispositivo": atuador, "ligado": desejado,
                                                          "regra": regra["nome"], "valor_sensor": valor})
        log.info("Regra '%s': %s -> %s (sensor %.2f)", regra["nome"], atuador, desejado, valor)


async def _persistir(m: dict) -> None:
    c = m["conteudo"]
    if m["tipo"] == "alerta":
        if c["acao"] in ("fechado", "alterado"):
            await db.pool.execute("UPDATE alertas SET fechado_em = now() WHERE dispositivo_id = $1 AND fechado_em IS NULL", m["dispositivo"])
        if c["acao"] in ("aberto", "alterado"):
            await db.pool.execute("INSERT INTO alertas (dispositivo_id, nivel, mensagem, saude, vida_util_h) VALUES ($1,$2,$3,$4,$5)",
                                  m["dispositivo"], c["nivel"], c["mensagem"], c.get("saude"), c.get("vida_util_h"))
    elif m["tipo"] == "progresso":
        await db.pool.execute(
            """UPDATE jobs SET status = $2, progresso = $3, mensagem = $4, resultado = COALESCE($5, resultado), atualizado_em = now()
               WHERE id = $1::uuid AND status NOT IN ('concluido', 'erro')""",  # progresso atrasado não reabre job terminado
            c["job_id"], c["status"], c["progresso"], c["mensagem"], c.get("resultado"))
    elif m["tipo"] == "modelo":
        async with db.pool.acquire() as conexao, conexao.transaction():
            await conexao.execute("UPDATE modelos SET em_uso = false")
            await conexao.execute("""INSERT INTO modelos (versao, metricas, em_uso) VALUES ($1, $2, true)
                                     ON CONFLICT (versao) DO UPDATE SET metricas = EXCLUDED.metricas, em_uso = true""", c["versao"], c)


async def _ao_regras(msg: aio_pika.abc.AbstractIncomingMessage) -> None:
    async with msg.process(requeue=False):
        m = mensagens.decodificar(msg.body)
        if m["tipo"] == "telemetria":
            if m["conteudo"].get("classe") == "atuador":
                estado.registrar_telemetria(m)
            else:
                await _aplicar_regras(m)
        else:
            await _persistir(m)


async def _ao_websocket(msg: aio_pika.abc.AbstractIncomingMessage) -> None:
    async with msg.process(requeue=False):
        m = mensagens.decodificar(msg.body)
        if m["tipo"] == "telemetria":
            estado.registrar_telemetria(m)
        elif m["tipo"] == "previsao":
            estado.ultimas_previsoes[m["dispositivo"]] = m
        estado.mensagens_recentes.appendleft({"routing_key": msg.routing_key, **m})
        await estado.conexoes.transmitir(json.dumps(m, ensure_ascii=False))


async def iniciar() -> None:
    global exchange, _conexao
    _conexao = await rabbit.conectar("api")
    canal = await _conexao.channel()
    await canal.set_qos(prefetch_count=100)
    exchange = await rabbit.exchange_eventos(canal)
    await recarregar_regras()
    await (await canal.get_queue("q.regras", ensure=False)).consume(_ao_regras)
    await (await canal.get_queue("q.websocket", ensure=False)).consume(_ao_websocket)
    log.info("Consumindo q.regras e q.websocket")


async def encerrar() -> None:
    if _conexao:
        await _conexao.close()
