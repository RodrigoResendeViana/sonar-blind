// Sonar Bordo: o bipper na cabine. Recebe o aviso da API, toca, acende o LED, mostra a
// parada no OLED e publica o "ciente" quando o motorista aperta o botão.
//   LIVRE --(alerta)--> ALERTA --(botão)--> CIENTE_ENVIADO --(3 s)--> LIVRE
//   ALERTA sem botão por 2 min --> LIVRE
#include <Arduino.h>
#include <ArduinoJson.h>
#include <WiFi.h>

#include "../comum/rede.h"
#include "../comum/sinal.h"
#include "../comum/texto.h"
#include "config.h"
#include "secrets.h"

#if SONAR_OLED
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Wire.h>
#endif

namespace {

enum class Estado : uint8_t { LIVRE, ALERTA, CIENTE_ENVIADO };

const char* nomeEstado(Estado estado) {
  switch (estado) {
    case Estado::LIVRE: return "livre";
    case Estado::ALERTA: return "alerta";
    case Estado::CIENTE_ENVIADO: return "ciente_enviado";
  }
  return "?";
}

struct Alerta {
  String esperaId;
  String paradaNome;
  String linha;
  int paradasAte = 0;
};

const uint16_t TOQUE_ALERTA[] = {200, 150, 200, 150, 200, 4100};  // 3 bipes a cada ~5 s
const uint16_t TOQUE_CIENTE[] = {80, 80};

String topicoAlerta, topicoCiente, topicoStatus;
Estado estado = Estado::LIVRE;
Alerta alerta;
uint32_t desdeMs = 0;
uint32_t ultimoStatusMs = 0;
uint32_t ultimoDesenhoMs = 0;
bool redesenhar = true;

bool botaoUltimaLeitura = HIGH;
bool botaoEstavel = HIGH;
uint32_t botaoMudouMs = 0;

Sinal led(PINO_LED_BORDO);
Sinal buzzer(PINO_BUZZER_BORDO);

#if SONAR_OLED
Adafruit_SSD1306 tela(128, 64, &Wire, -1);
bool telaOk = false;
#endif

void ir(Estado novo) {
  Serial.printf("[bordo] %s -> %s\n", nomeEstado(estado), nomeEstado(novo));
  estado = novo;
  desdeMs = millis();
  redesenhar = true;
  switch (novo) {
    case Estado::LIVRE:
      led.desligar();
      buzzer.desligar();
      break;
    case Estado::ALERTA:
      led.fixo();
      TOCAR(buzzer, TOQUE_ALERTA, true);
      break;
    case Estado::CIENTE_ENVIADO:
      led.desligar();
      TOCAR(buzzer, TOQUE_CIENTE, false);
      break;
  }
}

void publicarStatus() {
  JsonDocument dados;
  dados["online"] = true;
  dados["estado"] = nomeEstado(estado);
  dados["rssi"] = WiFi.RSSI();
  dados["uptime_s"] = millis() / 1000;
  dados["fila"] = rede::tamanhoFila();
  dados["versao"] = VERSAO_FIRMWARE;
  rede::publicar(topicoStatus.c_str(), dados, true, false);
  ultimoStatusMs = millis();
  redesenhar = true;
}

void aoReceber(const char* topico, const JsonDocument& dados) {
  if (topicoAlerta != topico) return;
  alerta.esperaId = dados["espera_id"] | "";
  alerta.paradaNome = dados["parada_nome"] | "";
  alerta.linha = dados["linha"] | "";
  alerta.paradasAte = dados["paradas_ate"] | 0;
  Serial.printf("[bordo] alerta: ponto %s, linha %s\n", alerta.paradaNome.c_str(), alerta.linha.c_str());
  ir(Estado::ALERTA);
}

void enviarCiente() {
  JsonDocument dados;
  dados["espera_id"] = alerta.esperaId;
  const String agora = rede::iso(time(nullptr));
  if (agora.length()) dados["horario"] = agora;
  rede::publicar(topicoCiente.c_str(), dados, false, true);  // guarda se o Wi-Fi cair
  ir(Estado::CIENTE_ENVIADO);
}

// true uma vez por aperto, com 40 ms de debounce
bool botaoApertado() {
  const bool leitura = digitalRead(PINO_BOTAO);
  if (leitura != botaoUltimaLeitura) {
    botaoUltimaLeitura = leitura;
    botaoMudouMs = millis();
  }
  if (millis() - botaoMudouMs > 40 && leitura != botaoEstavel) {
    botaoEstavel = leitura;
    return botaoEstavel == LOW;
  }
  return false;
}

void desenhar() {
#if SONAR_OLED
  if (!telaOk || (!redesenhar && millis() - ultimoDesenhoMs < 1000)) return;
  redesenhar = false;
  ultimoDesenhoMs = millis();
  tela.clearDisplay();
  tela.setTextColor(SSD1306_WHITE);
  tela.setCursor(0, 0);
  switch (estado) {
    case Estado::LIVRE:
      tela.setTextSize(1);
      tela.println("SONAR BORDO");
      tela.println();
      tela.print("Onibus ");
      tela.println(SONAR_PREFIXO);
      tela.println(rede::mqttConectado() ? "Conectado" : "Sem conexao");
      break;
    case Estado::ALERTA:
      tela.setTextSize(1);
      tela.println("PASSAGEIRO CEGO");
      tela.println("NO PONTO:");
      tela.println(paraAscii(alerta.paradaNome));
      tela.print("a ");
      tela.print(alerta.paradasAte);
      tela.println(" parada(s)");
      tela.println();
      tela.println("Aperte CIENTE");
      break;
    case Estado::CIENTE_ENVIADO:
      tela.setTextSize(2);
      tela.println("CIENTE");
      tela.println("ENVIADO");
      break;
  }
  tela.display();
#endif
}

}  // namespace

void setup() {
  Serial.begin(115200);
  pinMode(PINO_BOTAO, INPUT_PULLUP);
  led.iniciar();
  buzzer.iniciar();
#if SONAR_OLED
  Wire.begin(PINO_SDA, PINO_SCL);
  telaOk = tela.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  if (!telaOk) Serial.println("[bordo] OLED não encontrado; seguindo sem display");
#endif

  const String base = String("sonar/onibus/") + SONAR_PREFIXO;
  topicoAlerta = base + "/alerta";
  topicoCiente = base + "/ciente";
  topicoStatus = base + "/status";

  static String clienteId = String("bordo-") + SONAR_PREFIXO;
  rede::iniciar({clienteId.c_str(), MQTT_USUARIO_BORDO, MQTT_SENHA_BORDO, topicoStatus.c_str()}, aoReceber,
                publicarStatus);
  rede::assinar(topicoAlerta.c_str());
  Serial.printf("[bordo] Sonar Bordo %s, ônibus %s\n", VERSAO_FIRMWARE, SONAR_PREFIXO);
}

void loop() {
  rede::loop();
  const bool apertou = botaoApertado();
  if (estado == Estado::ALERTA) {
    if (apertou) {
      enviarCiente();
    } else if (millis() - desdeMs > ALERTA_MAX_MS) {
      ir(Estado::LIVRE);
    }
  } else if (estado == Estado::CIENTE_ENVIADO && millis() - desdeMs > 3000) {
    ir(Estado::LIVRE);
  }
  if (millis() - ultimoStatusMs > STATUS_MS) publicarStatus();
  led.atualizar();
  buzzer.atualizar();
  desenhar();
}
