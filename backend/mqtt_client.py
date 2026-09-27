"""Cliente MQTT: assina o tópico casa/temperatura e valida as leituras."""

import json

import paho.mqtt.client as mqtt

import config

# Faixa de medição do DHT22
TEMP_MIN = -40.0
TEMP_MAX = 80.0


def extrair_temperatura(payload: bytes) -> float | None:
    """Converte o payload {"temperatura": 25.4} em float. Retorna None se inválido."""
    try:
        dados = json.loads(payload.decode("utf-8"))
        valor = dados["temperatura"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    valor = float(valor)
    if not TEMP_MIN <= valor <= TEMP_MAX:  # também descarta NaN
        return None
    return valor


def iniciar(ao_receber) -> mqtt.Client:
    """Conecta ao broker em segundo plano e chama ao_receber(temperatura) a cada leitura válida."""
    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[MQTT] Falha na conexão: {reason_code}")
            return
        print(f"[MQTT] Conectado a {config.MQTT_HOST}:{config.MQTT_PORT}, assinando {config.MQTT_TOPIC}")
        client.subscribe(config.MQTT_TOPIC)

    def on_message(client, userdata, msg):
        temperatura = extrair_temperatura(msg.payload)
        if temperatura is None:
            print(f"[MQTT] Mensagem ignorada (inválida): {msg.payload!r}")
            return
        print(f"[MQTT] {msg.topic} -> {temperatura:.1f} °C")
        try:
            ao_receber(temperatura)
        except Exception as erro:  # não derruba o cliente MQTT se o InfluxDB falhar
            print(f"[MQTT] Erro ao processar a leitura: {erro}")

    cliente.on_connect = on_connect
    cliente.on_message = on_message
    # connect_async + loop_start: reconecta sozinho se o broker cair ou ainda não estiver no ar
    cliente.connect_async(config.MQTT_HOST, config.MQTT_PORT)
    cliente.loop_start()
    return cliente
