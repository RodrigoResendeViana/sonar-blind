// Sonar Ponto: o robô evoluído. Junta a leitura da câmera (MQTT) com o ultrassom e age
// sozinho: LED para o motorista, bip para o usuário achar o poste e evento de passagem
// (com o tempo parado) para a API.
//
// Máquina de estados:
//   OCIOSO --(cmd ativar)--> AGUARDANDO --(ultrassom: algo encostou)--> ONIBUS_DETECTADO
//   ONIBUS_DETECTADO --(foi embora)--> publica a passagem -->
//       linha certa? sim: AGUARDANDO_CONFIRMACAO (LED aceso)  não: AGUARDANDO
//   o usuário confirma o embarque ou o "não parou" no app; a API manda cmd desativar --> OCIOSO
//
// Botão no poste ("tem passageiro com deficiência visual aqui"): para quem está sem o app ou sem
// internet. Publica {"tipo":"botao"} e a API avisa os motoristas de todas as linhas do ponto. Mesmo
// sem rede, o LED já começa a piscar na hora, por 10 minutos.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include <math.h>

#include "../comum/mediana.h"
#include "../comum/rede.h"
#include "../comum/sinal.h"
#include "config.h"
#include "secrets.h"

namespace {

enum class Estado : uint8_t { OCIOSO, AGUARDANDO, ONIBUS_DETECTADO, AGUARDANDO_CONFIRMACAO };
enum class ModoLed : uint8_t { APAGADO, PULSANDO, FIXO, ERRO };

const char* nomeEstado(Estado estado) {
  switch (estado) {
    case Estado::OCIOSO: return "ocioso";
    case Estado::AGUARDANDO: return "aguardando";
    case Estado::ONIBUS_DETECTADO: return "onibus_detectado";
    case Estado::AGUARDANDO_CONFIRMACAO: return "aguardando_confirmacao";
  }
  return "?";
}

struct LeituraCamera {
  String linha;
  float confianca = 0;
  uint32_t recebidaMs = 0;
  time_t passouEm = 0;
  bool valida = false;
};

const uint16_t PULSO[] = {500, 500};
const uint16_t ERRO_REDE[] = {100, 100, 100, 700};
const uint16_t BIP_LOCALIZAR[] = {150, 150, 150, 150, 150, 600};
const uint16_t BIP_E_O_SEU[] = {900, 100};
const uint16_t BIP_BOTAO[] = {80, 80, 80, 80};

String topicoCmd, topicoEvento, topicoStatus, topicoVisao, topicoCamera;

Estado estado = Estado::OCIOSO;
ModoLed modoLed = ModoLed::ERRO;
String esperaId;
String linhasAlvo[MAX_LINHAS];
uint8_t qtdLinhas = 0;
time_t expiraEm = 0;
float limiarCm = LIMIAR_PADRAO_CM;

Mediana<5> mediana;
uint32_t ultimaMedicaoMs = 0;
uint32_t pertoDesdeMs = 0;
uint32_t longeDesdeMs = 0;
uint32_t inicioPresencaMs = 0;
time_t inicioPresenca = 0;
uint32_t confirmacaoDesdeMs = 0;
bool linhaCertaSinalizada = false;

LeituraCamera melhor;    // melhor leitura enquanto o ônibus está no ponto
LeituraCamera pendente;  // leitura que chegou antes do ultrassom perceber algo
bool cameraOnline = false;
uint32_t cameraVistaMs = 0;
uint32_t ultimoStatusMs = 0;
bool botaoAnterior = HIGH;
uint32_t botaoMudouMs = 0;
uint32_t pedidoLocalAteMs = 0;  // pedido do botão enquanto a API não responde

Sinal led(PINO_LED_PONTO);
Sinal buzzer(PINO_BUZZER_PONTO);

bool cameraOk() { return cameraOnline && millis() - cameraVistaMs < 90000UL; }

bool ehLinhaAlvo(const String& linha) {
  for (uint8_t i = 0; i < qtdLinhas; i++) {
    if (linhasAlvo[i].equalsIgnoreCase(linha)) return true;
  }
  return false;
}

void ir(Estado novo) {
  if (novo == estado) return;
  Serial.printf("[ponto] %s -> %s\n", nomeEstado(estado), nomeEstado(novo));
  estado = novo;
  pertoDesdeMs = 0;
  longeDesdeMs = 0;
  if (novo != Estado::ONIBUS_DETECTADO) {
    melhor = LeituraCamera();
    linhaCertaSinalizada = false;
  }
  if (novo == Estado::OCIOSO) {
    pendente = LeituraCamera();
    esperaId = "";
    qtdLinhas = 0;
    expiraEm = 0;
    buzzer.desligar();
  }
  if (novo == Estado::AGUARDANDO_CONFIRMACAO) confirmacaoDesdeMs = millis();
}

void publicarStatus() {
  JsonDocument dados;
  dados["online"] = true;
  dados["estado"] = nomeEstado(estado);
  dados["rssi"] = WiFi.RSSI();
  dados["uptime_s"] = millis() / 1000;
  dados["fila"] = rede::tamanhoFila();
  dados["camera_ok"] = cameraOk();
  dados["versao"] = VERSAO_FIRMWARE;
  rede::publicar(topicoStatus.c_str(), dados, true, false);
  ultimoStatusMs = millis();
}

void publicarPassagem(const LeituraCamera& leitura, float tempoParado, time_t passouEm) {
  JsonDocument dados;
  dados["espera_id"] = esperaId;
  if (leitura.valida) {
    dados["linha_lida"] = leitura.linha;
    dados["confianca"] = leitura.confianca;
  } else {
    dados["linha_lida"] = nullptr;
    dados["confianca"] = 0;
  }
  const String quando = rede::iso(passouEm);
  if (quando.length()) dados["passou_em"] = quando;
  dados["tempo_parado_s"] = roundf(tempoParado * 10) / 10;
  dados["parou"] = tempoParado >= PAROU_MIN_S;
  dados["camera_ok"] = cameraOk();
  rede::publicar(topicoEvento.c_str(), dados, false, true);  // guarda se o Wi-Fi cair
  Serial.printf("[ponto] passagem: %s, %.1f s parado\n", leitura.valida ? leitura.linha.c_str() : "sem leitura",
                tempoParado);
}

void sinalizarLinhaCerta() {
  if (linhaCertaSinalizada) return;
  linhaCertaSinalizada = true;
  TOCAR(buzzer, BIP_E_O_SEU, false);  // bip longo: é o seu
}

void iniciarPresenca(uint32_t desdeMs) {
  inicioPresencaMs = desdeMs;
  inicioPresenca = time(nullptr) - (millis() - desdeMs) / 1000;
  ir(Estado::ONIBUS_DETECTADO);
  if (pendente.valida && millis() - pendente.recebidaMs <= LEITURA_PENDENTE_MAX_MS) {
    melhor = pendente;  // a câmera viu o letreiro antes de o ônibus encostar
    if (ehLinhaAlvo(melhor.linha)) sinalizarLinhaCerta();
  }
  pendente = LeituraCamera();
}

void encerrarPresenca(uint32_t fimMs) {
  const float tempoParado = (fimMs - inicioPresencaMs) / 1000.0f;
  const bool certa = melhor.valida && ehLinhaAlvo(melhor.linha);
  publicarPassagem(melhor, tempoParado, inicioPresenca);
  ir(certa ? Estado::AGUARDANDO_CONFIRMACAO : Estado::AGUARDANDO);
}

float medirCm() {
  digitalWrite(PINO_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PINO_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PINO_TRIG, LOW);
  const unsigned long duracao = pulseIn(PINO_ECHO, HIGH, 30000UL);  // 30 ms: até ~5 m
  return duracao == 0 ? NAN : duracao / 58.0f;
}

void processarUltrassom() {
  const uint32_t agora = millis();
  if (agora - ultimaMedicaoMs < INTERVALO_LEITURA_MS) return;
  ultimaMedicaoMs = agora;
  const float cm = medirCm();
  mediana.adicionar(isnan(cm) ? 400.0f : cm);  // sem eco = nada na frente
  if (!mediana.cheia()) return;
  const float distancia = mediana.valor();

  if (estado == Estado::AGUARDANDO || estado == Estado::AGUARDANDO_CONFIRMACAO) {
    if (distancia < limiarCm) {
      if (pertoDesdeMs == 0) pertoDesdeMs = agora;
      if (agora - pertoDesdeMs >= PRESENCA_MIN_MS) iniciarPresenca(pertoDesdeMs);
    } else {
      pertoDesdeMs = 0;
    }
  } else if (estado == Estado::ONIBUS_DETECTADO) {
    if (distancia > limiarCm + HISTERESE_CM) {
      if (longeDesdeMs == 0) longeDesdeMs = agora;
      if (agora - longeDesdeMs >= AUSENCIA_MIN_MS) encerrarPresenca(longeDesdeMs);
    } else {
      longeDesdeMs = 0;
    }
    if (estado == Estado::ONIBUS_DETECTADO && agora - inicioPresencaMs > PRESENCA_MAX_MS) encerrarPresenca(agora);
  }
}

void aoLerCamera(const JsonDocument& dados) {
  cameraOnline = true;
  cameraVistaMs = millis();
  const char* linha = dados["linha_lida"] | "";
  if (*linha == '\0' || estado == Estado::OCIOSO) return;
  LeituraCamera leitura;
  leitura.linha = linha;
  leitura.confianca = dados["confianca"] | 0.0f;
  leitura.recebidaMs = millis();
  leitura.passouEm = time(nullptr);
  leitura.valida = true;

  if (estado == Estado::ONIBUS_DETECTADO) {
    const bool novaEhAlvo = ehLinhaAlvo(leitura.linha);
    const bool melhorEhAlvo = melhor.valida && ehLinhaAlvo(melhor.linha);
    if (!melhor.valida || (novaEhAlvo && !melhorEhAlvo) ||
        (novaEhAlvo == melhorEhAlvo && leitura.confianca > melhor.confianca)) {
      melhor = leitura;
    }
    if (novaEhAlvo) sinalizarLinhaCerta();
  } else if (!pendente.valida || ehLinhaAlvo(leitura.linha) || !ehLinhaAlvo(pendente.linha)) {
    pendente = leitura;
  }
}

void lerBotao() {
  const bool leitura = digitalRead(PINO_BOTAO_PONTO);
  if (leitura == botaoAnterior || millis() - botaoMudouMs < 50) return;  // filtro de 50 ms
  botaoMudouMs = millis();
  botaoAnterior = leitura;
  if (leitura != LOW) return;  // só na hora de apertar
  JsonDocument dados;
  dados["tipo"] = "botao";
  const String quando = rede::iso(time(nullptr));
  if (quando.length()) dados["em"] = quando;
  rede::publicar(topicoEvento.c_str(), dados, false, true);  // guarda e manda quando a rede voltar
  TOCAR(buzzer, BIP_BOTAO, false);  // "recebi"
  if (estado == Estado::OCIOSO) {
    pedidoLocalAteMs = millis() + BOTAO_LOCAL_MS;
    ir(Estado::AGUARDANDO);  // LED piscando já, sem esperar a API
  }
  Serial.println("[ponto] botão apertado");
}

void aoComando(const JsonDocument& dados) {
  const char* acao = dados["acao"] | "";
  if (strcmp(acao, "ativar") == 0) {
    pedidoLocalAteMs = 0;  // a API assumiu
    const time_t expira = rede::deIso(dados["expira_em"] | "");
    if (expira != 0 && rede::horaValida() && expira < time(nullptr)) {
      ir(Estado::OCIOSO);  // comando retido de uma espera que já venceu
      return;
    }
    esperaId = dados["espera_id"] | "";
    qtdLinhas = 0;
    for (JsonVariantConst linha : dados["linhas_alvo"].as<JsonArrayConst>()) {
      if (qtdLinhas < MAX_LINHAS) linhasAlvo[qtdLinhas++] = linha | "";
    }
    expiraEm = expira;
    if (estado == Estado::OCIOSO) {
      ir(Estado::AGUARDANDO);
      TOCAR(buzzer, BIP_LOCALIZAR, false);  // o usuário acha o poste pelo som
    }
  } else if (strcmp(acao, "desativar") == 0) {
    ir(Estado::OCIOSO);
  } else if (strcmp(acao, "localizar") == 0) {
    TOCAR(buzzer, BIP_LOCALIZAR, false);
  } else if (strcmp(acao, "config") == 0) {
    const float limiar = dados["limiar_cm"] | 0.0f;
    if (limiar >= 5 && limiar <= 400) limiarCm = limiar;
    Serial.printf("[ponto] limiar = %.0f cm\n", limiarCm);
  }
}

void aoReceber(const char* topico, const JsonDocument& dados) {
  if (topicoCmd == topico) {
    aoComando(dados);
  } else if (topicoVisao == topico) {
    aoLerCamera(dados);
  } else if (topicoCamera == topico) {
    cameraOnline = dados["online"] | false;
    cameraVistaMs = millis();
  }
}

void atualizarLed() {
  ModoLed desejado = ModoLed::APAGADO;
  if (!rede::wifiConectado()) {
    desejado = ModoLed::ERRO;  // Wi-Fi caiu: os eventos ficam guardados
  } else if (estado == Estado::AGUARDANDO_CONFIRMACAO ||
             (estado == Estado::ONIBUS_DETECTADO && linhaCertaSinalizada)) {
    desejado = ModoLed::FIXO;
  } else if (estado != Estado::OCIOSO) {
    desejado = ModoLed::PULSANDO;  // sinal para o motorista: tem passageiro cego no ponto
  }
  if (desejado == modoLed) return;
  modoLed = desejado;
  switch (modoLed) {
    case ModoLed::APAGADO: led.desligar(); break;
    case ModoLed::PULSANDO: TOCAR(led, PULSO, true); break;
    case ModoLed::FIXO: led.fixo(); break;
    case ModoLed::ERRO: TOCAR(led, ERRO_REDE, true); break;
  }
}

void verificarPrazos() {
  const uint32_t agora = millis();
  // leitura de linha-alvo sem ônibus encostado: passou pela faixa de fora, sem parar
  if (pendente.valida && estado != Estado::ONIBUS_DETECTADO && agora - pendente.recebidaMs > LEITURA_PENDENTE_MAX_MS) {
    if (ehLinhaAlvo(pendente.linha)) publicarPassagem(pendente, 0, pendente.passouEm);
    pendente = LeituraCamera();
  }
  if (estado == Estado::AGUARDANDO_CONFIRMACAO && agora - confirmacaoDesdeMs > CONFIRMACAO_MS) ir(Estado::AGUARDANDO);
  if (estado != Estado::OCIOSO && expiraEm != 0 && rede::horaValida() && time(nullptr) > expiraEm) {
    ir(Estado::OCIOSO);
  }
  if (pedidoLocalAteMs != 0 && esperaId.length() == 0 && (int32_t)(agora - pedidoLocalAteMs) > 0) {
    pedidoLocalAteMs = 0;
    ir(Estado::OCIOSO);  // pedido só local que venceu
  }
  if (agora - ultimoStatusMs > STATUS_MS) publicarStatus();
}

}  // namespace

void setup() {
  Serial.begin(115200);
  pinMode(PINO_TRIG, OUTPUT);
  pinMode(PINO_ECHO, INPUT);
  pinMode(PINO_BOTAO_PONTO, INPUT_PULLUP);
  led.iniciar();
  buzzer.iniciar();

  const String base = String("sonar/parada/") + SONAR_PARADA;
  topicoCmd = base + "/cmd";
  topicoEvento = base + "/evento";
  topicoStatus = base + "/status";
  topicoVisao = base + "/visao";
  topicoCamera = base + "/camera/status";

  static String clienteId = String("ponto-") + SONAR_PARADA;
  rede::iniciar({clienteId.c_str(), MQTT_USUARIO_PONTO, MQTT_SENHA_PONTO, topicoStatus.c_str()}, aoReceber,
                publicarStatus);
  rede::assinar(topicoCmd.c_str());
  rede::assinar(topicoVisao.c_str());
  rede::assinar(topicoCamera.c_str());
  Serial.printf("[ponto] Sonar Ponto %s, parada %s\n", VERSAO_FIRMWARE, SONAR_PARADA);
}

void loop() {
  rede::loop();
  lerBotao();
  if (estado != Estado::OCIOSO) processarUltrassom();
  verificarPrazos();
  atualizarLed();
  led.atualizar();
  buzzer.atualizar();
}
