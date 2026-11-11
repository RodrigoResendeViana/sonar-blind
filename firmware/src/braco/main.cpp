// Sonar Braço (Maker Lab): cabeça pan-tilt com 2 servos que segue o letreiro do ônibus.
// A câmera e o YOLO rodam no notebook (edge/); este ESP32 só recebe a posição do letreiro em
// sonar/parada/<id>/mira ({"alvo":true,"x":0..1,"y":0..1}) e move os servos com suavização.
//
//   REPOUSO --(cmd ativar)--> PROCURANDO (varre de um lado para o outro)
//   PROCURANDO/REPOUSO --(mira com alvo)--> SEGUINDO
//   SEGUINDO --(alvo:false ou 3 s sem mira)--> PROCURANDO (com espera) ou REPOUSO
//   qualquer --(mexeu no potenciômetro)--> MANUAL por 10 s (demo sem câmera, inclusive no Wokwi)
#include <Arduino.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include <WiFi.h>

#include "../comum/rede.h"
#include "config.h"
#include "secrets.h"

namespace {

enum class Modo : uint8_t { REPOUSO, PROCURANDO, SEGUINDO, MANUAL };

const char* nomeModo(Modo modo) {
  switch (modo) {
    case Modo::REPOUSO: return "repouso";
    case Modo::PROCURANDO: return "procurando";
    case Modo::SEGUINDO: return "seguindo";
    case Modo::MANUAL: return "manual";
  }
  return "?";
}

Servo servoPan, servoTilt;
String topicoMira, topicoCmd, topicoStatus;

Modo modo = Modo::REPOUSO;
bool esperaAtiva = false;
float pan = PAN_CENTRO, tilt = TILT_CENTRO;          // posição atual (graus)
float panAlvo = PAN_CENTRO, tiltAlvo = TILT_CENTRO;  // para onde está indo
int8_t sentidoVarredura = 1;
uint32_t ultimaMiraMs = 0, manualAteMs = 0, ultimoPassoMs = 0, ultimoStatusMs = 0;
int potAnterior = -1;

float limitar(float valor, float minimo, float maximo) { return valor < minimo ? minimo : valor > maximo ? maximo : valor; }

void publicarStatus() {
  JsonDocument doc;
  doc["online"] = true;
  doc["modo"] = nomeModo(modo);
  doc["pan"] = static_cast<int>(pan);
  doc["tilt"] = static_cast<int>(tilt);
  doc["espera"] = esperaAtiva;
  doc["versao"] = VERSAO_FIRMWARE;
  rede::publicar(topicoStatus.c_str(), doc, true, false);
  ultimoStatusMs = millis();
}

void ir(Modo novo) {
  if (novo == modo) return;
  Serial.printf("[braco] %s -> %s\n", nomeModo(modo), nomeModo(novo));
  modo = novo;
  if (modo == Modo::REPOUSO) {
    panAlvo = PAN_CENTRO;
    tiltAlvo = TILT_CENTRO;
  }
  publicarStatus();
}

// x e y são o centro do letreiro no quadro (0,5 = meio).
void aoMirar(const JsonDocument& dados) {
  if (modo == Modo::MANUAL) return;
  if (!(dados["alvo"] | false)) {
    ir(esperaAtiva ? Modo::PROCURANDO : Modo::REPOUSO);
    return;
  }
  const float x = limitar(dados["x"] | 0.5f, 0, 1);
  const float y = limitar(dados["y"] | 0.5f, 0, 1);
#if CAMERA_NO_BRACO
  // a câmera gira junto: corrige o erro até o letreiro ficar no meio do quadro (malha fechada)
  const float erroX = x - 0.5f, erroY = y - 0.5f;
  if (fabsf(erroX) > ZONA_MORTA) panAlvo = limitar(pan - GANHO_PAN * erroX, PAN_MIN, PAN_MAX);
  if (fabsf(erroY) > ZONA_MORTA) tiltAlvo = limitar(tilt + GANHO_TILT * erroY, TILT_MIN, TILT_MAX);
#else
  // câmera parada ao lado: aponta direto para a posição do letreiro (malha aberta)
  panAlvo = PAN_MAX - x * (PAN_MAX - PAN_MIN);
  tiltAlvo = TILT_MIN + y * (TILT_MAX - TILT_MIN);
#endif
  ultimaMiraMs = millis();
  ir(Modo::SEGUINDO);
}

void aoComando(const JsonDocument& dados) {
  const char* acao = dados["acao"] | "";
  if (strcmp(acao, "ativar") == 0) {
    esperaAtiva = true;
    if (modo == Modo::REPOUSO) ir(Modo::PROCURANDO);
  } else if (strcmp(acao, "desativar") == 0) {
    esperaAtiva = false;
    if (modo != Modo::MANUAL) ir(Modo::REPOUSO);
  }
}

void aoReceber(const char* topico, const JsonDocument& dados) {
  if (topicoMira == topico) {
    aoMirar(dados);
  } else if (topicoCmd == topico) {
    aoComando(dados);
  }
}

void lerPotenciometro() {
#if !USAR_POT
  return;
#endif
  const int leitura = analogRead(PINO_POT);  // 0..4095
  if (potAnterior >= 0 && abs(leitura - potAnterior) > 200) {
    manualAteMs = millis() + MANUAL_MS;
    ir(Modo::MANUAL);
  }
  potAnterior = leitura;
  if (modo == Modo::MANUAL) {
    panAlvo = PAN_MIN + (leitura / 4095.0f) * (PAN_MAX - PAN_MIN);
    if (millis() > manualAteMs) ir(esperaAtiva ? Modo::PROCURANDO : Modo::REPOUSO);
  }
}

void passo() {
  const uint32_t agora = millis();
  if (agora - ultimoPassoMs < PASSO_MS) return;
  ultimoPassoMs = agora;

  if (modo == Modo::SEGUINDO && agora - ultimaMiraMs > PERDEU_ALVO_MS) {
    ir(esperaAtiva ? Modo::PROCURANDO : Modo::REPOUSO);
  }
  if (modo == Modo::PROCURANDO) {
    panAlvo = pan + sentidoVarredura * VELOCIDADE_VARREDURA;
    if (panAlvo >= PAN_MAX || panAlvo <= PAN_MIN) sentidoVarredura = -sentidoVarredura;
    panAlvo = limitar(panAlvo, PAN_MIN, PAN_MAX);
    tiltAlvo = TILT_CENTRO;
  }
  // suavização: no máximo VELOCIDADE_MAX graus por passo (sem tranco no servo nem na fonte)
  pan += limitar(panAlvo - pan, -VELOCIDADE_MAX, VELOCIDADE_MAX);
  tilt += limitar(tiltAlvo - tilt, -VELOCIDADE_MAX, VELOCIDADE_MAX);
  servoPan.write(static_cast<int>(pan + 0.5f));
  servoTilt.write(static_cast<int>(tilt + 0.5f));
}

}  // namespace

void setup() {
  Serial.begin(115200);
  ESP32PWM::allocateTimer(0);
  servoPan.setPeriodHertz(50);
  servoTilt.setPeriodHertz(50);
  servoPan.attach(PINO_SERVO_PAN, 500, 2400);
  servoTilt.attach(PINO_SERVO_TILT, 500, 2400);
  servoPan.write(PAN_CENTRO);
  servoTilt.write(TILT_CENTRO);

  const String base = String("sonar/parada/") + SONAR_PARADA;
  topicoMira = base + "/mira";
  topicoCmd = base + "/cmd";
  topicoStatus = base + "/braco/status";

  static String clienteId = String("braco-") + SONAR_PARADA;
  rede::iniciar({clienteId.c_str(), MQTT_USUARIO_BRACO, MQTT_SENHA_BRACO, topicoStatus.c_str()}, aoReceber,
                publicarStatus);
  rede::assinar(topicoMira.c_str());
  rede::assinar(topicoCmd.c_str());
  Serial.printf("[braco] Sonar Braco %s, parada %s\n", VERSAO_FIRMWARE, SONAR_PARADA);
}

void loop() {
  rede::loop();
  lerPotenciometro();
  passo();
  if (millis() - ultimoStatusMs > STATUS_MS) publicarStatus();
}
