"""Serviço Laboratório: executa jobs demorados em segundo plano, vindos do RabbitMQ.

q.jobs.lab    -> gera dados sintéticos massivos (e uma amostra no bucket "lab" do InfluxDB)
q.jobs.treino -> treina os modelos de regressão e publica modelo.atualizado

O progresso é publicado em progresso.<job_id>; a API nunca fica esperando o job.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import aio_pika
import gerador
import treino
from aiot_common import equipamento, features, mensagens, rabbit, saude
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [lab] %(message)s")
log = logging.getLogger()


def gravar_amostra_influx() -> int:
    """Grava uma amostra do dataset no bucket "lab", separado dos dados ao vivo."""
    with InfluxDBClient(url=os.getenv("INFLUX_URL", "http://influxdb:8086"), token=os.environ["INFLUX_TOKEN"], org="casa") as cliente:
        buckets = cliente.buckets_api()
        if buckets.find_bucket_by_name("lab") is None:
            org_id = cliente.organizations_api().find_organizations(org="casa")[0].id
            buckets.create_bucket(bucket_name="lab", org_id=org_id)
        cliente.delete_api().delete("1970-01-01T00:00:00Z", datetime.now(timezone.utc).isoformat(),
                                    '_measurement="sintetico"', bucket="lab", org="casa")
        escrita = cliente.write_api(write_options=SYNCHRONOUS)
        agora = datetime.now(timezone.utc)
        pontos, lote = 0, []
        amostra = list(gerador.amostra_para_influx())
        ultimo_passo = max((p for _, p, *_ in amostra), default=0)
        com_falha = {e for e, _, _, s, _ in amostra if s < 100}
        for e, passo, v, s, rul in amostra:
            instante = agora - timedelta(minutes=equipamento.PASSO_MINUTOS * (ultimo_passo - passo))
            nome_eq = f"eq-{e:03d}-com-falha" if e in com_falha else f"eq-{e:03d}-saudavel"
            ponto = Point("sintetico").tag("equipamento", nome_eq).field("saude", s).field("vida_util_h", rul)
            for (nome, valor), (minimo, maximo) in zip(zip(equipamento.VARIAVEIS, v), features.FAIXAS):
                # a amostra é só para visualizar: pula faltantes (NaN) e valores absurdos,
                # que continuam no dataset de treino
                if valor == valor and minimo <= valor <= maximo:
                    ponto = ponto.field(nome, float(valor))
            lote.append(ponto.time(instante, WritePrecision.S))
            if len(lote) == 5000:
                escrita.write(bucket="lab", record=lote)
                pontos += len(lote)
                lote = []
        if lote:
            escrita.write(bucket="lab", record=lote)
            pontos += len(lote)
        return pontos


async def main() -> None:
    asyncio.create_task(saude.manter_batimento())
    conexao = await rabbit.conectar("lab")
    canal = await conexao.channel()
    await canal.set_qos(prefetch_count=1)  # um job por vez
    exchange = await rabbit.exchange_eventos(canal)
    loop = asyncio.get_running_loop()

    async def executar(msg: aio_pika.abc.AbstractIncomingMessage) -> None:
        async with msg.process(requeue=False):
            pedido = mensagens.decodificar(msg.body)
            job_id = pedido["conteudo"]["job_id"]
            tipo = pedido["conteudo"]["tipo"]
            parametros = pedido["conteudo"].get("parametros", {})
            ultimo = [0.0]

            async def publicar(status: str, pct: int, texto: str, resultado: dict | None = None) -> None:
                conteudo = {"job_id": job_id, "tipo": tipo, "status": status, "progresso": pct, "mensagem": texto}
                if resultado is not None:
                    conteudo["resultado"] = resultado
                await rabbit.publicar(exchange, f"progresso.{job_id}", mensagens.criar("progresso", conteudo))

            def progresso(pct: int, texto: str, forcar: bool = False) -> None:  # chamado na thread do job
                if forcar or time.time() - ultimo[0] > 0.7 or pct >= 100:
                    ultimo[0] = time.time()
                    asyncio.run_coroutine_threadsafe(publicar("executando", pct, texto), loop)

            log.info("Iniciando job %s (%s)", job_id, tipo)
            await publicar("executando", 0, "Job iniciado")
            try:
                if tipo == "geracao":
                    resultado = await asyncio.to_thread(gerador.gerar, parametros, progresso)
                    progresso(95, "Gravando amostra no bucket lab do InfluxDB", forcar=True)
                    resultado["pontos_bucket_lab"] = await asyncio.to_thread(gravar_amostra_influx)
                    texto = f"{resultado['leituras']:,} leituras geradas".replace(",", ".")
                else:
                    resultado = await asyncio.to_thread(treino.treinar, parametros, progresso)
                    texto = f"Modelos v{resultado['versao']} treinados"
                    if resultado["em_uso"]:
                        await rabbit.publicar(exchange, "modelo.atualizado", mensagens.criar("modelo", resultado))
                    else:
                        texto += " (não venceram a base; versão anterior mantida)"
                await publicar("concluido", 100, texto, resultado)
                log.info("Job %s concluído: %s", job_id, texto)
            except Exception as erro:
                log.exception("Job %s falhou", job_id)
                await publicar("erro", 100, str(erro))

    for nome in ("q.jobs.lab", "q.jobs.treino"):
        fila = await canal.get_queue(nome, ensure=False)
        await fila.consume(executar)
    log.info("Aguardando jobs de geração e treino")
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
