#pragma once
// Wi-Fi, relógio (NTP), MQTT com TLS e fila de eventos para quando a conexão cai.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <time.h>

namespace rede {

struct Config {
  const char* clienteId;
  const char* usuario;
  const char* senha;
  const char* topicoStatus;  // recebe o "testamento" {"online":false} se a conexão cair
};

using AoReceber = void (*)(const char* topico, const JsonDocument& dados);
using AoConectar = void (*)();

void iniciar(const Config& config, AoReceber aoReceber, AoConectar aoConectar);
void assinar(const char* topico);  // o texto precisa continuar vivo (ex.: String global)
void loop();

// Publica JSON. Com guardarSeFalhar, o evento vai para a fila e sai quando a conexão voltar.
bool publicar(const char* topico, const JsonDocument& dados, bool retido, bool guardarSeFalhar);

bool wifiConectado();
bool mqttConectado();
uint8_t tamanhoFila();
bool horaValida();
String iso(time_t instante);    // "2026-11-08T18:45:00Z", ou "" sem hora válida
time_t deIso(const char* texto);  // 0 se não der para ler

}  // namespace rede
