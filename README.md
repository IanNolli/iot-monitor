# Smart Home — Monitoramento de Temperatura

Projeto IoT da disciplina **Desenvolvimento de Software para Web II — 1º Bimestre**.

## Problema

Uma residência precisa acompanhar a temperatura de um ambiente e consultar o histórico de medições de forma simples.

## Solução

Um ESP32 simulado no Wokwi, com sensor DHT22, publica a temperatura a cada 5 segundos via MQTT. O Mosquitto atua como broker. Um backend Python recebe as mensagens, valida os dados e os grava no InfluxDB. Uma API Python entrega esses dados a um dashboard em Vue.js 3, que mostra a temperatura atual, o horário da última leitura e um gráfico com o histórico.

## Arquitetura

```
ESP32 + DHT22 (Wokwi) → MQTT (casa/temperatura) → Mosquitto → Python → InfluxDB → API Python → Vue.js
```

| Componente    | Tecnologia                          | Responsabilidade                              |
|---------------|-------------------------------------|-----------------------------------------------|
| Dispositivo   | ESP32 + DHT22 no Wokwi (VS Code)    | Ler a temperatura e publicar via MQTT          |
| Broker        | Mosquitto                           | Receber e distribuir as mensagens              |
| Backend       | Python + paho-mqtt                  | Assinar o tópico, validar e gravar             |
| Banco         | InfluxDB 2.x                        | Armazenar a série temporal                     |
| API           | Python + Flask                      | Entregar valor atual e histórico em JSON       |
| Frontend      | Vue 3 + TypeScript + Vite + Chart.js | Exibir o dashboard                            |

**Formato da mensagem MQTT:** tópico `casa/temperatura`, payload `{"temperatura": 25.4}`.

**Estrutura no InfluxDB:** bucket `iot`, measurement `temperatura`, field `valor`. O timestamp é o momento da gravação.

**Endpoints:**

| Método | Rota                          | Resposta                                                                 |
|--------|-------------------------------|--------------------------------------------------------------------------|
| GET    | `/api/temperatura`            | `{"temperatura": 24.5, "timestamp": "2026-09-27T18:06:22+00:00"}` (404 se ainda não houver leituras) |
| GET    | `/api/temperatura/historico`  | Lista com até 50 leituras da última hora, em ordem cronológica           |

## Estrutura do repositório

```
iot-monitor/
├── backend/
│   ├── app.py              # inicia o cliente MQTT e a API Flask
│   ├── mqtt_client.py      # assina casa/temperatura e valida o payload
│   ├── influx_storage.py   # grava e consulta no InfluxDB
│   ├── config.py           # lê o arquivo .env
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.vue
│   │   ├── components/     # TemperaturaAtual.vue, GraficoHistorico.vue
│   │   ├── services/api.ts # chamadas aos endpoints
│   │   ├── types.ts
│   │   └── formatacao.ts
│   ├── package.json
│   └── vite.config.ts      # proxy /api → backend (porta 8000)
├── wokwi/
│   ├── src/main.cpp        # firmware do ESP32
│   ├── diagram.json        # ESP32 + DHT22 (GPIO 15)
│   ├── platformio.ini
│   └── wokwi.toml
├── mosquitto/
│   └── mosquitto.conf
└── README.md
```

## Pré-requisitos

- Python 3.10 ou superior
- Node.js 20.19+ ou 22.12+
- Mosquitto 2.x
- InfluxDB 2.x (OSS)
- VS Code com as extensões **Wokwi Simulator** e **PlatformIO IDE**

## Configuração inicial (uma única vez)

### InfluxDB

1. Inicie o servidor: `influxd`
2. Acesse http://localhost:8086 e faça a configuração inicial com **Organization** `casa` e **Bucket** `iot`.
3. Copie o **API Token** exibido ao final.

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    |   Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # Windows: copy .env.example .env
```

Edite `backend/.env` e cole o token em `INFLUX_TOKEN=`.

### Frontend

```bash
cd frontend
npm install
```

## Execução

Inicie os componentes nesta ordem, cada um em seu terminal, a partir da raiz do repositório.

```bash
# 1. Broker
mosquitto -c mosquitto/mosquitto.conf -v

# 2. Banco
influxd

# 3. Backend (com o ambiente virtual ativado)
cd backend
python app.py

# 4. Frontend
cd frontend
npm run dev
```

5. **ESP32:** no VS Code, abra a pasta `wokwi/`, compile com o PlatformIO (Build), abra `diagram.json` e inicie a simulação.

Abra o dashboard em http://localhost:5173.

> Se o Mosquitto acusar porta 1883 em uso, pare o serviço instalado automaticamente: `net stop mosquitto` (Windows, como administrador) ou `sudo systemctl stop mosquitto` (Linux).

## Testes

| Parte          | Como testar                                                                 | Resultado esperado                              |
|----------------|-----------------------------------------------------------------------------|-------------------------------------------------|
| ESP32/Wokwi    | Monitor serial da simulação                                                 | `Publicado casa/temperatura -> {"temperatura": 24.5}` a cada 5 s |
| MQTT/Mosquitto | `mosquitto_sub -h localhost -t casa/temperatura -v`                         | Mensagens do ESP32 chegando                      |
| Python         | Terminal do `python app.py`                                                 | `[MQTT] casa/temperatura -> 24.5 °C` e `[InfluxDB] Leitura gravada` |
| InfluxDB       | Data Explorer em http://localhost:8086 (bucket `iot`, measurement `temperatura`) | Leituras com timestamp                    |
| API atual      | http://localhost:8000/api/temperatura                                       | JSON com a última leitura                       |
| API histórico  | http://localhost:8000/api/temperatura/historico                             | Lista de leituras                               |
| Vue + gráfico  | http://localhost:5173                                                       | Temperatura atual, horário e gráfico atualizando |

**Teste sem o Wokwi:** a API e o dashboard podem ser testados publicando uma leitura manualmente.

```bash
# Linux/macOS
mosquitto_pub -h localhost -t casa/temperatura -m '{"temperatura": 26.3}'

# Windows (cmd)
mosquitto_pub -h localhost -t casa/temperatura -m "{\"temperatura\": 26.3}"
```

Mensagens inválidas (texto, valor fora da faixa −40 a 80 °C do DHT22) são descartadas e registradas no terminal do backend.

**Consulta direta ao InfluxDB (Flux):**

```
from(bucket: "iot")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "temperatura" and r._field == "valor")
```

## Fora do escopo do 1º bimestre

Login, usuários, múltiplos sensores, atuadores, comunicação bidirecional, Docker, deploy, CI/CD, notificações, WebSockets e múltiplas páginas. Podem ser evoluções futuras.
