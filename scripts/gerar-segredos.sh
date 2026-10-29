#!/bin/sh
# Gera o arquivo .env com senhas e chaves aleatórias para todos os serviços.
# Uso: ./scripts/gerar-segredos.sh           (não sobrescreve um .env existente)
#      ./scripts/gerar-segredos.sh --forcar  (gera tudo de novo; apague os volumes depois)
set -eu

cd "$(dirname "$0")/.."

if [ -f .env ] && [ "${1:-}" != "--forcar" ]; then
  echo ".env já existe. Use --forcar para gerar novos segredos."
  exit 0
fi

segredo() { openssl rand -hex "${1:-16}"; }

cat > .env <<EOF
# Gerado por scripts/gerar-segredos.sh em $(date '+%Y-%m-%d %H:%M'). NÃO versionar.

# Usuários da aplicação Web (login)
SENHA_ADMINISTRADOR=$(segredo 6)
SENHA_OPERADOR=$(segredo 6)
SENHA_VISUALIZADOR=$(segredo 6)
JWT_SEGREDO=$(segredo 32)

# Mosquitto (um usuário por cliente MQTT)
MQTT_SENHA_SIMULADOR=$(segredo)
MQTT_SENHA_GATEWAY=$(segredo)
MQTT_SENHA_MONITOR=$(segredo)

# RabbitMQ (administrador + um usuário por serviço)
RABBITMQ_SENHA_ADMIN=$(segredo)
RABBIT_SENHA_GATEWAY=$(segredo)
RABBIT_SENHA_GRAVADOR=$(segredo)
RABBIT_SENHA_INFERENCIA=$(segredo)
RABBIT_SENHA_LAB=$(segredo)
RABBIT_SENHA_API=$(segredo)

# PostgreSQL e pgAdmin
POSTGRES_SENHA=$(segredo)
PGADMIN_SENHA=$(segredo 8)

# InfluxDB
INFLUX_SENHA=$(segredo)
INFLUX_TOKEN=$(segredo 32)
EOF
chmod 600 .env

echo "Arquivo .env criado."
echo
echo "Usuários de demonstração da aplicação (http://localhost:8080):"
grep -E '^SENHA_' .env | sed -e 's/SENHA_ADMINISTRADOR=/  administrador -> /' \
                            -e 's/SENHA_OPERADOR=/  operador      -> /' \
                            -e 's/SENHA_VISUALIZADOR=/  visualizador  -> /'
echo
echo "pgAdmin (http://127.0.0.1:5050) abre direto; ao conectar no servidor AIoT, senha do PostgreSQL:"
echo "  $(grep '^POSTGRES_SENHA=' .env | cut -d= -f2)"
echo "RabbitMQ (http://127.0.0.1:15672) e InfluxDB (http://127.0.0.1:8086): usuário admin, senhas"
echo "  RABBITMQ_SENHA_ADMIN e INFLUX_SENHA do .env"
echo "As senhas ficam só no arquivo .env (ignorado pelo Git)."
