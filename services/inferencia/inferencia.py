"""Inferência em tempo real: aplica os modelos à telemetria do equipamento.

Consome q.inferencia (telemetria do compressor e avisos de modelo novo), mantém a janela
das últimas leituras, calcula as features com o MESMO código do treino e publica:
  previsao.<id>  saúde, vida útil restante, tendência
  alerta.<id>    abertura/mudança/fechamento de alertas, com histerese

Quando chega modelo.atualizado, recarrega os modelos sem reiniciar o serviço.
"""

import asyncio
import json
import logging
from collections import deque
from pathlib import Path

import aio_pika
import joblib
import numpy as np
from aiot_common import equipamento, features, mensagens, rabbit, saude

logging.basicConfig(level=logging.INFO, format="%(asctime)s [inferencia] %(message)s")
log = logging.getLogger()

DIR_MODELOS = Path("/modelos")
NIVEIS = ["normal", "atencao", "critico"]
SUBIR_APOS = 3    # previsões seguidas acima do limite para disparar
DESCER_APOS = 10  # previsões seguidas abaixo do limite para limpar


def nivel_bruto(saude_prev: float, vida_util: float) -> int:
    if saude_prev < 40 or vida_util < 24:
        return 2
    if saude_prev < 70 or vida_util < 72:
        return 1
    return 0


class Modelos:
    def __init__(self) -> None:
        self.versao: int | None = None
        self.vida_util = None
        self.saude = None

    def carregar(self) -> None:
        atual = DIR_MODELOS / "atual.json"
        if not atual.exists():
            log.info("Nenhum modelo treinado ainda; aguardando o primeiro treino")
            return
        info = json.loads(atual.read_text())
        if info["versao"] == self.versao:
            return
        diretorio = Path(info["diretorio"])
        self.vida_util = joblib.load(diretorio / "vida_util.joblib")["modelo"]
        self.saude = joblib.load(diretorio / "saude.joblib")["modelo"]
        self.versao = info["versao"]
        log.info("Modelos v%s carregados e em uso", self.versao)


class Equipamento:
    def __init__(self) -> None:
        self.janela: deque = deque(maxlen=features.JANELA)
        self.historico_saude: deque = deque(maxlen=12)
        self.suave: deque = deque(maxlen=5)
        self.nivel = 0
        self.contador = 0


async def main() -> None:
    asyncio.create_task(saude.manter_batimento())
    modelos = Modelos()
    modelos.carregar()
    estados: dict[str, Equipamento] = {}

    conexao = await rabbit.conectar("inferencia")
    canal = await conexao.channel()
    await canal.set_qos(prefetch_count=50)
    exchange = await rabbit.exchange_eventos(canal)
    fila = await canal.get_queue("q.inferencia", ensure=False)

    async def ao_receber(msg: aio_pika.abc.AbstractIncomingMessage) -> None:
        async with msg.process(requeue=False):
            m = mensagens.decodificar(msg.body)
            if m["tipo"] == "modelo":
                modelos.carregar()
                return
            dispositivo = m["dispositivo"]
            est = estados.setdefault(dispositivo, Equipamento())
            leitura = [m["conteudo"].get(v) for v in equipamento.VARIAVEIS]
            est.janela.append([np.nan if x is None else float(x) for x in leitura])
            if modelos.versao is None or len(est.janela) < features.JANELA // 2:
                return

            x = features.calcular(np.array(est.janela)[None, :, :])
            saude_prev = float(np.clip(modelos.saude.predict(x)[0], 0, 100))
            vida_prev = float(np.clip(modelos.vida_util.predict(x)[0], 0, 240))
            est.suave.append((saude_prev, vida_prev))
            saude_s = float(np.median([s for s, _ in est.suave]))
            vida_s = float(np.median([v for _, v in est.suave]))
            est.historico_saude.append(saude_s)
            # tendência: variação da saúde por hora simulada nas últimas previsões
            h = np.array(est.historico_saude)
            tendencia = float(np.polyfit(np.arange(len(h)) * equipamento.PASSO_MINUTOS / 60, h, 1)[0]) if len(h) >= 4 else 0.0

            await rabbit.publicar(exchange, f"previsao.{dispositivo}", mensagens.criar("previsao", {
                "saude": round(saude_s, 1), "vida_util_h": round(vida_s, 1), "tendencia_saude_h": round(tendencia, 2),
                "nivel": NIVEIS[est.nivel], "versao_modelo": modelos.versao,
            }, dispositivo))

            # Histerese: 3 previsões seguidas para piorar, 10 para melhorar
            alvo = nivel_bruto(saude_s, vida_s)
            if alvo == est.nivel:
                est.contador = 0
                return
            est.contador += 1
            if est.contador < (SUBIR_APOS if alvo > est.nivel else DESCER_APOS):
                return
            anterior, est.nivel, est.contador = est.nivel, alvo, 0
            acao = "aberto" if anterior == 0 else ("fechado" if alvo == 0 else "alterado")
            texto = {
                0: "Compressor voltou ao normal",
                1: f"Atenção: saúde {saude_s:.0f} e falha prevista em cerca de {vida_s:.0f} h",
                2: f"Crítico: saúde {saude_s:.0f}; o compressor deve falhar em cerca de {vida_s:.0f} h",
            }[alvo]
            await rabbit.publicar(exchange, f"alerta.{dispositivo}", mensagens.criar("alerta", {
                "acao": acao, "nivel": NIVEIS[alvo], "nivel_anterior": NIVEIS[anterior], "mensagem": texto,
                "saude": round(saude_s, 1), "vida_util_h": round(vida_s, 1),
            }, dispositivo))
            log.info("Alerta %s em %s: %s", acao, dispositivo, texto)

    await fila.consume(ao_receber)
    log.info("Inferência aguardando telemetria do equipamento")
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
