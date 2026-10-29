"""Simulador do dispositivo IoT da casa (substitui o ESP32 do 1º bimestre).

Publica telemetria no Mosquitto e escuta comandos. O tempo é acelerado:
cada ciclo representa 5 minutos simulados (1 dia simulado ~ 10 minutos reais),
para o ciclo dia/noite e a degradação do compressor aparecerem na demonstração.

Sensores:    temp-sala (°C), lum-sala (lux), pres-sala (0/1)
Equipamento: comp-geladeira (vibração mm/s, corrente A, temperatura °C)
Atuadores:   vent-sala (ventilador, regra automática), lamp-sala (lâmpada, comando Web)

Tópicos:  aiot/telemetria/<zona>/<tipo>/<id>     aiot/comando/<id>
"""

import json
import logging
import math
import os
import random
import threading
import time

import numpy as np
import paho.mqtt.client as mqtt
from aiot_common import equipamento, saude

logging.basicConfig(level=logging.INFO, format="%(asctime)s [simulador] %(message)s")
log = logging.getLogger()

INTERVALO = float(os.getenv("SIM_INTERVALO", "2"))
DURACAO_FALHA_DIAS = float(os.getenv("SIM_DURACAO_FALHA_DIAS", "1"))  # do início da falha até quebrar
rng = np.random.default_rng(int(os.getenv("SIM_SEMENTE", "42")))


class Casa:
    def __init__(self) -> None:
        self.passo = 8 * 60 // equipamento.PASSO_MINUTOS  # começa às 8h
        self.temp_sala = 24.0
        self.presenca = 0
        self.ventilador = False
        self.lampada = False
        self.params = {k: float(v[0]) for k, v in equipamento.sortear_parametros(rng).items()}
        self.degradacao = 0.0
        self.modo_falha: str | None = None
        self.lock = threading.Lock()

    # --- comandos recebidos ---
    def comando(self, dispositivo: str, conteudo: dict) -> list[str]:
        """Aplica o comando e devolve a lista de atuadores cujo estado mudou."""
        with self.lock:
            if dispositivo == "vent-sala":
                self.ventilador = bool(conteudo.get("ligado"))
                return ["vent-sala"]
            if dispositivo == "lamp-sala":
                self.lampada = bool(conteudo.get("ligado"))
                return ["lamp-sala"]
            if dispositivo == "simulador":
                acao = conteudo.get("acao")
                if acao == "injetar_falha":
                    modo = conteudo.get("modo", "rolamento")
                    if modo not in equipamento.MODOS_FALHA:
                        raise ValueError(f"modo de falha desconhecido: {modo}")
                    self.modo_falha = modo
                    self.degradacao = max(self.degradacao, 0.15)
                    log.info("Falha injetada no compressor: %s", modo)
                elif acao == "reparar":
                    self.modo_falha = None
                    self.degradacao = 0.0
                    log.info("Compressor reparado")
                return []
        raise ValueError(f"dispositivo sem comando: {dispositivo}")

    # --- um ciclo de simulação ---
    def avancar(self) -> list[tuple[str, dict]]:
        with self.lock:
            self.passo += 1
            hora = float(equipamento.hora_do_dia(self.passo))

            # Temperatura da sala: segue o ambiente (+2 °C); o ventilador puxa para baixo
            alvo = float(equipamento.temperatura_ambiente(self.passo)) + 2.0 + 0.5 * self.presenca
            if self.ventilador:
                alvo -= 5.0
            self.temp_sala += (alvo - self.temp_sala) * 0.08 + random.gauss(0, 0.05)

            # Luminosidade: luz do dia (6h–18h) + lâmpada
            sol = max(0.0, math.sin(math.pi * (hora - 6.0) / 12.0)) if 6.0 <= hora <= 18.0 else 0.0
            lux = 800.0 * sol + (350.0 if self.lampada else 0.0) + abs(random.gauss(2, 2))

            # Presença: mais provável à noite
            entrada = 0.08 if (hora >= 18 or hora < 7) else 0.03
            if self.presenca and random.random() < 0.04:
                self.presenca = 0
            elif not self.presenca and random.random() < entrada:
                self.presenca = 1

            # Compressor: degradação progressiva quando há falha
            if self.modo_falha:
                self.degradacao = min(1.0, self.degradacao + 1.0 / (DURACAO_FALHA_DIAS * equipamento.LEITURAS_POR_DIA))
            v = equipamento.valores(self.passo, self.params, self.degradacao, self.modo_falha, rng)
            comp = {nome: _imperfeito(float(v[i])) for i, nome in enumerate(equipamento.VARIAVEIS)}

            hora_txt = f"{int(hora):02d}:{int((hora % 1) * 60):02d}"
            return [
                ("sala/sensor/temp-sala", {"valor": round(self.temp_sala, 2), "unidade": "°C"}),
                ("sala/sensor/lum-sala", {"valor": round(lux, 1), "unidade": "lux"}),
                ("sala/sensor/pres-sala", {"valor": self.presenca, "unidade": ""}),
                ("cozinha/equipamento/comp-geladeira", comp),
                ("sala/atuador/vent-sala", {"ligado": self.ventilador}),
                ("sala/atuador/lamp-sala", {"ligado": self.lampada}),
                ("casa/relogio/simulador", {"hora_simulada": hora_txt}),
            ]

    def estado_atuador(self, dispositivo: str) -> tuple[str, dict]:
        ligado = self.ventilador if dispositivo == "vent-sala" else self.lampada
        return f"sala/atuador/{dispositivo}", {"ligado": ligado}


def _imperfeito(valor: float) -> float | None:
    """Sensores reais falham: algumas leituras somem e outras vêm absurdas."""
    sorteio = random.random()
    if sorteio < 0.005:
        return None
    if sorteio < 0.007:
        return round(valor * 25, 2)
    return round(valor, 3)


def main() -> None:
    casa = Casa()
    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="simulador-casa")
    cliente.username_pw_set("simulador", os.environ["MQTT_SENHA_SIMULADOR"])

    def publicar(caminho: str, payload: dict) -> None:
        cliente.publish(f"aiot/telemetria/{caminho}", json.dumps(payload), qos=0)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log.error("Falha ao conectar no Mosquitto: %s", reason_code)
            return
        log.info("Conectado ao Mosquitto; aguardando comandos em aiot/comando/#")
        client.subscribe("aiot/comando/#", qos=1)

    def on_message(client, userdata, msg):
        dispositivo = msg.topic.rsplit("/", 1)[-1]
        try:
            conteudo = json.loads(msg.payload)
            mudaram = casa.comando(dispositivo, conteudo)
            log.info("Comando recebido para %s: %s", dispositivo, conteudo)
            for d in mudaram:  # confirma o novo estado imediatamente
                publicar(*casa.estado_atuador(d))
        except (ValueError, json.JSONDecodeError) as erro:
            log.warning("Comando inválido em %s: %s", msg.topic, erro)

    cliente.on_connect = on_connect
    cliente.on_message = on_message
    cliente.connect_async(os.getenv("MQTT_HOST", "mosquitto"), 1883)
    cliente.loop_start()

    while True:
        inicio = time.monotonic()
        if cliente.is_connected():
            for caminho, payload in casa.avancar():
                publicar(caminho, payload)
            saude.ARQUIVO.write_text(str(time.time()))  # healthcheck: só fica saudável conectado
        time.sleep(max(0.0, INTERVALO - (time.monotonic() - inicio)))


if __name__ == "__main__":
    main()
