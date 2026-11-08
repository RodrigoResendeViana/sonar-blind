#include "rede.h"

#include <PubSubClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>

#include "certs.h"
#include "config.h"
#include "secrets.h"

namespace rede {
namespace {

#if MQTT_TLS
WiFiClientSecure clienteRede;
#else
WiFiClient clienteRede;
#endif
PubSubClient mqtt(clienteRede);

Config cfg{};
AoReceber aoReceber = nullptr;
AoConectar aoConectar = nullptr;

const char* assinaturas[8];
uint8_t qtdAssinaturas = 0;

uint32_t ultimaTentativaWifi = 0;
uint32_t ultimaTentativaMqtt = 0;

struct Pendente {
  String topico;
  String corpo;
};
Pendente fila[TAMANHO_FILA];
uint8_t inicioFila = 0;
uint8_t qtdFila = 0;

const char TESTAMENTO[] = "{\"online\":false}";

void enfileirar(const char* topico, const String& corpo) {
  if (qtdFila == TAMANHO_FILA) {  // fila cheia: descarta o mais antigo
    inicioFila = (inicioFila + 1) % TAMANHO_FILA;
    qtdFila--;
  }
  Pendente& p = fila[(inicioFila + qtdFila) % TAMANHO_FILA];
  p.topico = topico;
  p.corpo = corpo;
  qtdFila++;
  Serial.printf("[rede] sem conexão: evento guardado (%u na fila)\n", qtdFila);
}

void esvaziarFila() {
  while (qtdFila > 0 && mqtt.connected()) {
    Pendente& p = fila[inicioFila];
    if (!mqtt.publish(p.topico.c_str(), p.corpo.c_str(), false)) return;
    p.topico = "";
    p.corpo = "";
    inicioFila = (inicioFila + 1) % TAMANHO_FILA;
    qtdFila--;
  }
}

void aoChegarMensagem(char* topico, uint8_t* conteudo, unsigned int tamanho) {
  if (aoReceber == nullptr) return;
  JsonDocument dados;
  DeserializationError erro = deserializeJson(dados, conteudo, tamanho);
  if (erro) {
    Serial.printf("[rede] JSON inválido em %s: %s\n", topico, erro.c_str());
    return;
  }
  aoReceber(topico, dados);
}

void conectarMqtt() {
  Serial.printf("[rede] conectando ao MQTT %s:%d\n", MQTT_HOST, MQTT_PORTA);
  if (!mqtt.connect(cfg.clienteId, cfg.usuario, cfg.senha, cfg.topicoStatus, 1, true, TESTAMENTO)) {
    Serial.printf("[rede] MQTT recusou (estado %d)\n", mqtt.state());
    return;
  }
  Serial.println("[rede] MQTT conectado");
  for (uint8_t i = 0; i < qtdAssinaturas; i++) mqtt.subscribe(assinaturas[i], 1);
  if (aoConectar != nullptr) aoConectar();
  esvaziarFila();
}

}  // namespace

void iniciar(const Config& config, AoReceber receber, AoConectar conectar) {
  cfg = config;
  aoReceber = receber;
  aoConectar = conectar;
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
#ifdef SONAR_WOKWI
  WiFi.begin("Wokwi-GUEST", "", 6);
#else
  WiFi.begin(WIFI_SSID, WIFI_SENHA);
#endif
  configTime(0, 0, "pool.ntp.org", "time.google.com");  // UTC
#if MQTT_TLS
  clienteRede.setCACert(CA_RAIZES);
#endif
  mqtt.setServer(MQTT_HOST, MQTT_PORTA);
  mqtt.setCallback(aoChegarMensagem);
  mqtt.setBufferSize(1024);
  mqtt.setKeepAlive(30);
  mqtt.setSocketTimeout(10);
}

void assinar(const char* topico) {
  if (qtdAssinaturas < sizeof(assinaturas) / sizeof(assinaturas[0])) assinaturas[qtdAssinaturas++] = topico;
  if (mqtt.connected()) mqtt.subscribe(topico, 1);
}

void loop() {
  const uint32_t agora = millis();
  if (WiFi.status() != WL_CONNECTED) {
    if (agora - ultimaTentativaWifi > 10000) {
      ultimaTentativaWifi = agora;
      Serial.println("[rede] Wi-Fi fora, tentando de novo");
      WiFi.reconnect();
    }
    return;
  }
  if (!mqtt.connected()) {
    // o TLS confere a validade do certificado: espera o NTP (ou 30 s, no pior caso)
    if (agora - ultimaTentativaMqtt > 5000 && (horaValida() || agora > 30000)) {
      ultimaTentativaMqtt = agora;
      conectarMqtt();
    }
    return;
  }
  mqtt.loop();
}

bool publicar(const char* topico, const JsonDocument& dados, bool retido, bool guardarSeFalhar) {
  String corpo;
  serializeJson(dados, corpo);
  if (mqtt.connected() && qtdFila == 0 && mqtt.publish(topico, corpo.c_str(), retido)) return true;
  if (guardarSeFalhar) {
    enfileirar(topico, corpo);
    esvaziarFila();
  }
  return false;
}

bool wifiConectado() { return WiFi.status() == WL_CONNECTED; }

bool mqttConectado() { return mqtt.connected(); }

uint8_t tamanhoFila() { return qtdFila; }

bool horaValida() { return time(nullptr) > 1700000000; }

String iso(time_t instante) {
  if (instante < 1700000000) return "";
  struct tm partes;
  gmtime_r(&instante, &partes);
  char texto[24];
  strftime(texto, sizeof(texto), "%Y-%m-%dT%H:%M:%SZ", &partes);
  return String(texto);
}

time_t deIso(const char* texto) {
  int ano, mes, dia, hora, minuto, segundo;
  if (texto == nullptr || sscanf(texto, "%4d-%2d-%2dT%2d:%2d:%2d", &ano, &mes, &dia, &hora, &minuto, &segundo) != 6) {
    return 0;
  }
  struct tm partes = {};
  partes.tm_year = ano - 1900;
  partes.tm_mon = mes - 1;
  partes.tm_mday = dia;
  partes.tm_hour = hora;
  partes.tm_min = minuto;
  partes.tm_sec = segundo;
  return mktime(&partes);  // o fuso é UTC (configTime acima)
}

}  // namespace rede
