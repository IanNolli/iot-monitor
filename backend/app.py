"""Ponto de entrada do backend: inicia o cliente MQTT e a API.

Execução: python app.py
"""

from flask import Flask, jsonify

import config
import influx_storage
import mqtt_client

app = Flask(__name__)


@app.get("/api/temperatura")
def temperatura_atual():
    try:
        leitura = influx_storage.ultima()
    except Exception as erro:
        print(f"[API] Erro ao consultar o InfluxDB: {erro}")
        return jsonify({"erro": "Falha ao consultar o InfluxDB"}), 503
    if leitura is None:
        return jsonify({"erro": "Nenhuma leitura registrada"}), 404
    return jsonify(leitura)


@app.get("/api/temperatura/historico")
def temperatura_historico():
    try:
        leituras = influx_storage.historico()
    except Exception as erro:
        print(f"[API] Erro ao consultar o InfluxDB: {erro}")
        return jsonify({"erro": "Falha ao consultar o InfluxDB"}), 503
    return jsonify(leituras)


def ao_receber(temperatura: float) -> None:
    influx_storage.salvar(temperatura)
    print(f"[InfluxDB] Leitura gravada: {temperatura:.1f} °C")


if __name__ == "__main__":
    mqtt_client.iniciar(ao_receber)
    # debug=False evita o reloader do Flask, que iniciaria o cliente MQTT duas vezes
    app.run(host="127.0.0.1", port=config.API_PORT, debug=False)
