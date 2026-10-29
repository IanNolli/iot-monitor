"""Conexão com o RabbitMQ (aio-pika) usada por todos os serviços."""

import asyncio
import logging
import os

import aio_pika

from . import mensagens

log = logging.getLogger("rabbit")


def url_rabbit(servico: str) -> str:
    usuario = servico
    senha = os.environ[f"RABBIT_SENHA_{servico.upper()}"]
    host = os.getenv("RABBIT_HOST", "rabbitmq")
    vhost = os.getenv("RABBIT_VHOST", "aiot")
    return f"amqp://{usuario}:{senha}@{host}:5672/{vhost}"


async def conectar(servico: str) -> aio_pika.abc.AbstractRobustConnection:
    """Conecta com reconexão automática; tenta de novo até o broker estar pronto."""
    while True:
        try:
            conexao = await aio_pika.connect_robust(url_rabbit(servico), client_properties={"connection_name": servico})
            log.info("Conectado ao RabbitMQ como %s", servico)
            return conexao
        except Exception as erro:  # broker ainda subindo
            log.warning("RabbitMQ indisponível (%s); nova tentativa em 3 s", erro)
            await asyncio.sleep(3)


async def exchange_eventos(canal: aio_pika.abc.AbstractChannel) -> aio_pika.abc.AbstractExchange:
    # passive=True: os serviços não têm permissão de configurar; a topologia é criada pelo rabbit-init
    return await canal.get_exchange(mensagens.EXCHANGE, ensure=False)


async def publicar(exchange: aio_pika.abc.AbstractExchange, routing_key: str, mensagem: dict) -> None:
    await exchange.publish(
        aio_pika.Message(
            body=mensagens.codificar(mensagem),
            content_type="application/json",
            message_id=mensagem["id"],
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key=routing_key,
    )
