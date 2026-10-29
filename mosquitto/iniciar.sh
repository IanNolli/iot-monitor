#!/bin/sh
# Cria o arquivo de senhas a partir das variáveis de ambiente e inicia o broker.
set -eu
arquivo=/mosquitto/data/passwd
rm -f "$arquivo"
touch "$arquivo"
chmod 0700 "$arquivo"
chown mosquitto:mosquitto "$arquivo"
mosquitto_passwd -b "$arquivo" simulador "$MQTT_SENHA_SIMULADOR"
mosquitto_passwd -b "$arquivo" gateway "$MQTT_SENHA_GATEWAY"
mosquitto_passwd -b "$arquivo" monitor "$MQTT_SENHA_MONITOR"
exec mosquitto -c /mosquitto/config/mosquitto.conf
