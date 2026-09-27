# Smart Home — Monitoramento de Temperatura

Projeto IoT da disciplina **Desenvolvimento de Software para Web II — 1º Bimestre**.

## Problema

Uma residência precisa acompanhar a temperatura de um ambiente e consultar o histórico de medições de forma simples.

## Solução

Um ESP32 simulado no Wokwi, com sensor DHT22, publica leituras de temperatura via MQTT. O Mosquitto atua como broker. Um backend Python recebe as mensagens, valida os dados e os grava no InfluxDB. Uma API Python entrega esses dados a um dashboard em Vue.js 3, que exibe a temperatura atual e um gráfico com o histórico.

## Arquitetura

```
ESP32 + DHT22 (Wokwi) → MQTT (casa/temperatura) → Mosquitto → Python → InfluxDB → API Python → Vue.js
```

## Tecnologias

| Componente    | Tecnologia                       |
|---------------|----------------------------------|
| Dispositivo   | ESP32 + DHT22 no Wokwi (VS Code) |
| Broker        | Mosquitto                        |
| Backend / API | Python + paho-mqtt + FastAPI     |
| Banco         | InfluxDB 2.x                     |
| Frontend      | Vue 3 + TypeScript + Vite        |
| Gráfico       | Chart.js                         |

## Estrutura do repositório

```
iot-monitor/
├── backend/     # cliente MQTT, gravação no InfluxDB e API
├── frontend/    # dashboard Vue 3 + TypeScript + Vite
├── wokwi/       # simulação do ESP32 + DHT22
├── mosquitto/   # configuração do broker
└── README.md
```

## Status do desenvolvimento

- [x] Etapa 0 — Preparação do repositório
- [ ] Etapa 1 — ESP32 + Wokwi
- [ ] Etapa 2 — Mosquitto
- [ ] Etapa 3 — Backend Python + MQTT
- [ ] Etapa 4 — InfluxDB
- [ ] Etapa 5 — API Python
- [ ] Etapa 6 — Frontend Vue
- [ ] Etapa 7 — Integração completa
- [ ] Etapa 8 — Documentação final

As instruções de instalação, execução e teste serão adicionadas conforme cada etapa for concluída e testada.
