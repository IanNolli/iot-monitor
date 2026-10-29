"""Gravador: consome q.gravador e grava telemetria e previsões no InfluxDB (bucket iot).

measurement "telemetria": tags dispositivo, zona, classe; um field por variável numérica
measurement "previsao":   tag dispositivo; fields saude e vida_util_h
Falhas persistentes de gravação mandam a mensagem para a DLQ (rejeição sem requeue).
"""

import asyncio
import logging
import os
from datetime import datetime

import aio_pika
from aiot_common import mensagens, rabbit, saude
from influxdb_client import Point, WritePrecision
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync

logging.basicConfig(level=logging.INFO, format="%(asctime)s [gravador] %(message)s")
log = logging.getLogger()

BUCKET = os.getenv("INFLUX_BUCKET", "iot")
ORG = os.getenv("INFLUX_ORG", "casa")
IGNORAR = {"zona", "classe", "unidade"}


def para_ponto(m: dict) -> Point | None:
    instante = datetime.fromisoformat(m["instante"])
    c = m["conteudo"]
    if m["tipo"] == "telemetria":
        ponto = Point("telemetria").tag("dispositivo", m["dispositivo"]).tag("zona", c.get("zona", "")).tag("classe", c.get("classe", ""))
        campos = 0
        for nome, valor in c.items():
            if nome in IGNORAR or valor is None:
                continue
            if isinstance(valor, bool):
                ponto = ponto.field(nome, 1.0 if valor else 0.0)
                campos += 1
            elif isinstance(valor, (int, float)):
                ponto = ponto.field(nome, float(valor))
                campos += 1
        return ponto.time(instante, WritePrecision.MS) if campos else None
    if m["tipo"] == "previsao":
        return (Point("previsao").tag("dispositivo", m["dispositivo"])
                .field("saude", float(c["saude"])).field("vida_util_h", float(c["vida_util_h"]))
                .time(instante, WritePrecision.MS))
    return None


async def main() -> None:
    asyncio.create_task(saude.manter_batimento())
    influx = InfluxDBClientAsync(url=os.getenv("INFLUX_URL", "http://influxdb:8086"), token=os.environ["INFLUX_TOKEN"], org=ORG)
    escrita = influx.write_api()

    conexao = await rabbit.conectar("gravador")
    canal = await conexao.channel()
    await canal.set_qos(prefetch_count=200)
    fila = await canal.get_queue("q.gravador", ensure=False)

    async def ao_receber(msg: aio_pika.abc.AbstractIncomingMessage) -> None:
        async with msg.process(requeue=False):
            ponto = para_ponto(mensagens.decodificar(msg.body))
            if ponto is None:
                return
            for tentativa in range(3):
                try:
                    await escrita.write(bucket=BUCKET, record=ponto)
                    return
                except Exception as erro:
                    log.warning("Falha ao gravar no InfluxDB (tentativa %d): %s", tentativa + 1, erro)
                    await asyncio.sleep(2)
            raise RuntimeError("InfluxDB indisponível; mensagem enviada para a DLQ")

    await fila.consume(ao_receber)
    log.info("Gravando telemetria no InfluxDB (bucket %s)", BUCKET)
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
