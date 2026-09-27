// Smart Home — Monitoramento de Temperatura
// ESP32 + DHT22: lê a temperatura a cada 5 s e publica em casa/temperatura.

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>

// ---------- Configuração ----------
#define DHT_PIN 15
#define DHT_TYPE DHT22

const char* WIFI_SSID     = "Wokwi-GUEST";  // rede virtual do Wokwi
const char* WIFI_PASSWORD = "";

// Etapa 1: broker público, apenas para testar a publicação.
// Etapa 2: será trocado por "host.wokwi.internal" (Mosquitto local).
const char*    MQTT_HOST  = "test.mosquitto.org";
const uint16_t MQTT_PORT  = 1883;
const char*    MQTT_TOPIC = "casa/temperatura";

const unsigned long INTERVALO_MS = 5000;

// ---------- Objetos globais ----------
WiFiClient   wifiClient;
PubSubClient mqtt(wifiClient);
DHT          dht(DHT_PIN, DHT_TYPE);

unsigned long ultimaLeitura = 0;

void conectarWiFi() {
  Serial.print("Conectando ao Wi-Fi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, 6);  // canal 6 acelera a conexão no Wokwi
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
    Serial.print(".");
  }
  Serial.println(" conectado");
}

void conectarMQTT() {
  while (!mqtt.connected()) {
    Serial.printf("Conectando ao broker %s:%u... ", MQTT_HOST, MQTT_PORT);
    // ID aleatório evita conflito com outros clientes no mesmo broker
    String clientId = "esp32-casa-" + String((uint32_t)esp_random(), HEX);
    if (mqtt.connect(clientId.c_str())) {
      Serial.println("conectado");
    } else {
      Serial.printf("falhou (rc=%d), nova tentativa em 2 s\n", mqtt.state());
      delay(2000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  dht.begin();
  conectarWiFi();
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) conectarWiFi();
  if (!mqtt.connected()) conectarMQTT();
  mqtt.loop();

  if (millis() - ultimaLeitura < INTERVALO_MS) return;
  ultimaLeitura = millis();

  float temperatura = dht.readTemperature();
  if (isnan(temperatura)) {
    Serial.println("Erro ao ler o DHT22");
    return;
  }

  char payload[32];
  snprintf(payload, sizeof(payload), "{\"temperatura\": %.1f}", temperatura);

  bool ok = mqtt.publish(MQTT_TOPIC, payload);
  Serial.printf("%s %s -> %s\n", ok ? "Publicado" : "FALHA ao publicar", MQTT_TOPIC, payload);
}
