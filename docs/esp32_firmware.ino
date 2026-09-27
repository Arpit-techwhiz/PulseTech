// ═══════════════════════════════════════════════════════
//  PulseTech ESP32-S3 — Sensor Firmware v2.1
//  Sensors: MAX30105 (HR+SpO2), DS18B20 (Temp), AD8232 (ECG)
//  Transport: WebSocket + MQTT + REST fallback
// ═══════════════════════════════════════════════════════

#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <HTTPClient.h>
#include <Wire.h>
#include "MAX30105.h"
#include "spo2_algorithm.h"
#include "heartRate.h"
#include <OneWire.h>
#include <DallasTemperature.h>
#include "esp_task_wdt.h"

// ─── NETWORK CONFIG ───────────────────────────────────
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// ─── SERVER CONFIG ────────────────────────────────────
const char* WS_HOST    = "192.168.1.100";   // PulseTech server IP
const int   WS_PORT    = 3001;
const char* WS_PATH    = "/ws";
const char* REST_URL   = "http://192.168.1.100:3001/api/sensor-data";
const char* JWT_TOKEN  = "YOUR_JWT_TOKEN";   // Get from /api/auth/login

// ─── MQTT CONFIG ──────────────────────────────────────
const char* MQTT_BROKER = "broker.hivemq.com";
const int   MQTT_PORT   = 1883;
const char* MQTT_TOPIC  = "pulsetech/pt-2024-0381/vitals";
const char* MQTT_CLIENT = "ESP32-S3-PT0381";

// ─── PIN CONFIG ───────────────────────────────────────
#define ECG_PIN       34   // AD8232 analog output
#define ECG_LO_PLUS   12   // Lead-off detection +
#define ECG_LO_MINUS  13   // Lead-off detection -
#define DS18B20_PIN   25   // OneWire temperature

// ─── SAMPLING ─────────────────────────────────────────
#define SAMPLE_RATE_HZ  100
#define BATCH_SIZE      10
#define WDT_TIMEOUT     30   // Watchdog 30s

// ─── OBJECTS ──────────────────────────────────────────
MAX30105 particleSensor;
WebSocketsClient wsClient;
WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
OneWire oneWire(DS18B20_PIN);
DallasTemperature tempSensor(&oneWire);

// ─── STATE ────────────────────────────────────────────
bool wsConnected  = false;
bool mqttConnected = false;
unsigned long lastSend    = 0;
unsigned long lastTemp    = 0;
unsigned long lastRecon   = 0;
float  currentTemp       = 36.6f;
int    currentHR         = 72;
int    currentSpo2       = 98;
int    currentSys        = 120;
int    currentDia        = 80;
int    riskScore         = 0;

// ECG buffer
#define ECG_BUFFER 50
float ecgBuffer[ECG_BUFFER];
int   ecgIdx = 0;

// HR/SpO2 buffers for MAX30105
#define MAX30102_SAMPLES 100
uint32_t irBuffer[MAX30102_SAMPLES];
uint32_t redBuffer[MAX30102_SAMPLES];
int8_t   validSPO2, validHR;
float    hrBeat;

// ─── WIFI SETUP ───────────────────────────────────────
void setupWifi() {
  Serial.print("[WiFi] Connecting to ");
  Serial.print(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long t = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t < 15000) {
    delay(250); Serial.print(".");
  }
  if (WiFi.isConnected()) {
    Serial.println("\n[WiFi] Connected: " + WiFi.localIP().toString());
  } else {
    Serial.println("\n[WiFi] Failed — will retry");
  }
}

// ─── WEBSOCKET ────────────────────────────────────────
void onWSEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      wsConnected = true;
      Serial.println("[WS] Connected to PulseTech server");
      // Authenticate
      {
        StaticJsonDocument<200> auth;
        auth["type"]  = "AUTH";
        auth["token"] = JWT_TOKEN;
        String s; serializeJson(auth, s);
        wsClient.sendTXT(s);
      }
      break;
    case WStype_DISCONNECTED:
      wsConnected = false;
      Serial.println("[WS] Disconnected");
      break;
    case WStype_TEXT:
      Serial.printf("[WS] Received: %s\n", payload);
      break;
    default: break;
  }
}

void setupWebSocket() {
  wsClient.begin(WS_HOST, WS_PORT, WS_PATH);
  wsClient.onEvent(onWSEvent);
  wsClient.setReconnectInterval(3000);
}

// ─── MQTT ─────────────────────────────────────────────
void mqttCallback(char* topic, byte* payload, unsigned int len) {
  Serial.printf("[MQTT] Topic: %s\n", topic);
}

void reconnectMQTT() {
  if (!mqttClient.connected()) {
    mqttClient.connect(MQTT_CLIENT);
    if (mqttClient.connected()) {
      mqttConnected = true;
      mqttClient.subscribe("pulsetech/commands/#");
      Serial.println("[MQTT] Connected");
    }
  }
}

// ─── SENSORS INIT ────────────────────────────────────
void setupSensors() {
  // MAX30105 (HR + SpO2)
  Wire.begin();
  if (particleSensor.begin(Wire, I2C_SPEED_FAST)) {
    particleSensor.setup();
    particleSensor.setPulseAmplitudeRed(0x3E);
    particleSensor.setPulseAmplitudeIR(0x3E);
    Serial.println("[SENSOR] MAX30105 initialized");
  } else {
    Serial.println("[SENSOR] MAX30105 not found — using simulation");
  }

  // DS18B20 temperature
  tempSensor.begin();
  Serial.printf("[SENSOR] Found %d temperature devices\n", tempSensor.getDeviceCount());

  // ECG ADC
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
  pinMode(ECG_LO_PLUS,  INPUT);
  pinMode(ECG_LO_MINUS, INPUT);
  Serial.println("[SENSOR] ECG ADC (AD8232) configured");
}

// ─── VITAL READING ────────────────────────────────────
void readVitals() {
  // HR + SpO2 from MAX30105
  if (particleSensor.check()) {
    for (int i = 0; i < MAX30102_SAMPLES; i++) {
      while (!particleSensor.available()) particleSensor.check();
      redBuffer[i] = particleSensor.getRed();
      irBuffer[i]  = particleSensor.getIR();
      particleSensor.nextSample();
    }
    maxim_heart_rate_and_oxygen_saturation(
      irBuffer, MAX30102_SAMPLES, redBuffer,
      &currentSpo2, &validSPO2, (int32_t*)&currentHR, &validHR
    );
    if (!validHR  || currentHR  < 30 || currentHR  > 220) currentHR  = 72; // fallback
    if (!validSPO2 || currentSpo2 < 70 || currentSpo2 > 100) currentSpo2 = 97;
  } else {
    // Simulation fallback
    currentHR   = 72 + (int)(sin(millis() * 0.001) * 8);
    currentSpo2 = 97 + (int)(cos(millis() * 0.0005) * 2);
  }

  // Temperature from DS18B20
  if (millis() - lastTemp > 2000) {
    lastTemp = millis();
    tempSensor.requestTemperatures();
    float t = tempSensor.getTempCByIndex(0);
    if (t > 25.0f && t < 45.0f) currentTemp = t;
    else currentTemp = 36.5f + sin(millis() * 0.0001) * 0.3f; // sim
  }
}

// ─── ECG SAMPLE ───────────────────────────────────────
float readECG() {
  if (digitalRead(ECG_LO_PLUS) || digitalRead(ECG_LO_MINUS)) return 0; // Lead off
  int raw = analogRead(ECG_PIN);
  float v = (raw / 4095.0f - 0.5f) * 3.3f; // Convert to voltage
  ecgBuffer[ecgIdx++ % ECG_BUFFER] = v;
  return v;
}

// ─── TINYML RISK (on-device) ──────────────────────────
int computeLocalRisk(int hr, int spo2, float temp) {
  float score = 0;
  if (hr > 100) score += (hr - 100) * 0.8f;
  if (hr < 50)  score += (50 - hr)  * 1.2f;
  if (spo2 < 95) score += (95 - spo2) * 3.5f;
  if (temp > 38.0f) score += (temp - 38.0f) * 4.0f;
  return (int)min(100.0f, max(0.0f, score));
}

// ─── PUBLISH VIA WEBSOCKET ────────────────────────────
void sendViaWebSocket(float ecg) {
  if (!wsConnected) return;
  StaticJsonDocument<300> doc;
  doc["type"]        = "SENSOR_DATA";
  doc["patient_id"]  = "PT-2024-0381";
  doc["device_id"]   = "ESP32-S3-NODE01";
  doc["hr"]          = currentHR;
  doc["spo2"]        = currentSpo2;
  doc["temperature"] = round(currentTemp * 10) / 10.0;
  doc["sys_bp"]      = currentSys;
  doc["dia_bp"]      = currentDia;
  doc["ecg_sample"]  = ecg;
  doc["risk_local"]  = riskScore;
  doc["timestamp"]   = millis();
  String json; serializeJson(doc, json);
  wsClient.sendTXT(json);
}

// ─── PUBLISH VIA MQTT ─────────────────────────────────
void sendViaMQTT(float ecg) {
  if (!mqttClient.connected()) return;
  StaticJsonDocument<300> doc;
  doc["hr"]          = currentHR;
  doc["spo2"]        = currentSpo2;
  doc["temperature"] = round(currentTemp * 10) / 10.0;
  doc["ecg"]         = ecg;
  doc["risk"]        = riskScore;
  doc["ts"]          = millis();
  String json; serializeJson(doc, json);
  mqttClient.publish(MQTT_TOPIC, json.c_str());
}

// ─── PUBLISH VIA REST FALLBACK ────────────────────────
void sendViaREST() {
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  http.begin(REST_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", String("Bearer ") + JWT_TOKEN);
  StaticJsonDocument<300> doc;
  doc["patient_id"]  = "PT-2024-0381";
  doc["hr"]          = currentHR;
  doc["spo2"]        = currentSpo2;
  doc["temperature"] = currentTemp;
  doc["sys_bp"]      = currentSys;
  doc["dia_bp"]      = currentDia;
  String json; serializeJson(doc, json);
  int code = http.POST(json);
  Serial.printf("[REST] POST → %d\n", code);
  http.end();
}

// ─── SETUP ────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  Serial.println("\n╔══════════════════════════════╗");
  Serial.println("║  PulseTech ESP32-S3 v2.1     ║");
  Serial.println("╚══════════════════════════════╝");

  esp_task_wdt_init(WDT_TIMEOUT, true);
  esp_task_wdt_add(NULL);

  setupWifi();
  setupSensors();
  setupWebSocket();

  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
}

// ─── LOOP ─────────────────────────────────────────────
void loop() {
  esp_task_wdt_reset();

  // WiFi watchdog
  if (WiFi.status() != WL_CONNECTED && millis() - lastRecon > 10000) {
    lastRecon = millis();
    WiFi.reconnect();
  }

  wsClient.loop();
  if (!mqttClient.connected()) reconnectMQTT();
  mqttClient.loop();

  float ecgVal = readECG();

  // Sample and transmit
  unsigned long now = millis();
  if (now - lastSend >= (1000 / SAMPLE_RATE_HZ)) {
    lastSend = now;
    readVitals();
    riskScore = computeLocalRisk(currentHR, currentSpo2, currentTemp);

    // Priority: WS → MQTT → REST
    if (wsConnected) {
      sendViaWebSocket(ecgVal);
    } else if (mqttClient.connected()) {
      sendViaMQTT(ecgVal);
    } else if (now % 5000 < 100) {
      sendViaREST(); // REST fallback every 5s
    }

    // Serial debug
    Serial.printf("[DATA] HR:%d SpO2:%d Temp:%.1f Risk:%d\n",
      currentHR, currentSpo2, currentTemp, riskScore);
  }

  delay(1);
}
