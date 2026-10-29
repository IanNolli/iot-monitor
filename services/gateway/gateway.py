"""Gateway MQTT <-> RabbitMQ.

IoT -> aplicação: lê aiot/telemetria/<zona>/<tipo>/<id> no Mosquitto, valida, coloca no
formato único de mensagem e publica em aiot.eventos com a routing key
telemetria.<zona>.<tipo>.<id>. Mensagens inválidas vão para a DLQ, preservadas.

Aplicação -> IoT: consome a fila q.comandos e publica em aiot/comando/<id>.
"""

import asyncio
import json
import logging
import os
import re

import aio_pika
import aiomqtt
from aiot_common import mensagens, rabbit, saude

logging.basicConfig(level=logging.INFO, format="%(asctime)s [gateway] %(message)s")
log = logging.getLogger()

TOPICO = re.compile(r"^aiot/telemetria/([a-z0-9-]+)/(sensor|atuador|equipamento|relogio)/([a-z0-9-]+)$")


async def enviar_dlq(dlx: aio_pika.abc.AbstractExchange, corpo: bytes, motivo: str, origem: str) -> None:
    await dlx.publish(
        aio_pika.Message(body=corpo, headers={"motivo": motivo, "origem": origem}, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
        routing_key="",
    )
    log.warning("Mensagem enviada para a DLQ (%s): %s", motivo, origem)


async def tratar_telemetria(msg: aiomqtt.Message, exchange, dlx) -> None:
    topico = str(msg.topic)
    corpo = msg.payload if isinstance(msg.payload, bytes) else str(msg.payload).encode()
    casamento = TOPICO.match(topico)
    if not casamento:
        await enviar_dlq(dlx, corpo, "tópico fora do padrão", topico)
        return
    zona, classe, dispositivo = casamento.groups()
    try:
        payload = json.loads(corpo)
        if not isinstance(payload, dict):
            raise ValueError("payload não é objeto JSON")
    except ValueError as erro:
        await enviar_dlq(dlx, corpo, f"JSON inválido: {erro}", topico)
        return
    conteudo = {"zona": zona, "classe": classe, **payload}
    mensagem = mensagens.criar("telemetria", conteudo, dispositivo)
    await rabbit.publicar(exchange, f"telemetria.{zona}.{classe}.{dispositivo}", mensagem)


async def main() -> None:
    asyncio.create_task(saude.manter_batimento())
    conexao = await rabbit.conectar("gateway")
    canal = await conexao.channel()
    await canal.set_qos(prefetch_count=20)
    exchange = await rabbit.exchange_eventos(canal)
    dlx = await canal.get_exchange(mensagens.EXCHANGE_DLX, ensure=False)
    fila_comandos = await canal.get_queue("q.comandos", ensure=False)

    while True:
        try:
            async with aiomqtt.Client(
                os.getenv("MQTT_HOST", "mosquitto"), 1883,
                username="gateway", password=os.environ["MQTT_SENHA_GATEWAY"], identifier="gateway-aiot",
            ) as mqtt:
                await mqtt.subscribe("aiot/telemetria/#")
                log.info("Conectado ao Mosquitto; repassando telemetria para o RabbitMQ")

                async def ao_comando(msg: aio_pika.abc.AbstractIncomingMessage) -> None:
                    # Exceção dentro do bloco -> rejeitada sem requeue -> vai para a DLQ
                    async with msg.process(requeue=False):
                        comando = mensagens.decodificar(msg.body)
                        dispositivo = comando["dispositivo"]
                        if not dispositivo or not re.fullmatch(r"[a-z0-9-]+", dispositivo):
                            raise ValueError("comando sem dispositivo válido")
                        await mqtt.publish(f"aiot/comando/{dispositivo}", json.dumps(comando["conteudo"]), qos=1)
                        log.info("Comando entregue a %s: %s", dispositivo, comando["conteudo"])

                tag = await fila_comandos.consume(ao_comando)
                try:
                    async for msg in mqtt.messages:
                        await tratar_telemetria(msg, exchange, dlx)
                finally:
                    await fila_comandos.cancel(tag)
        except aiomqtt.MqttError as erro:
            log.warning("Conexão MQTT perdida (%s); reconectando em 3 s", erro)
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
