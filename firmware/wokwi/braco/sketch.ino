// Sonar Braço no Wokwi pelo navegador (wokwi.com), sem instalar nada.
// É a versão em um arquivo só de firmware/src/braco/main.cpp, para a cabeça pan-tilt simulada seguir
// o letreiro que a câmera (ex.: o celular) vê de verdade. A visão roda no notebook (edge/); o ESP32
// só recebe a posição do letreiro em sonar/parada/demo/mira ({"alvo":true,"x":0..1,"y":0..1}).
//
// Como usar:
//   1. wokwi.com > New Project > ESP32. Cole este arquivo em sketch.ino e o diagram.json desta pasta
//      em diagram.json. Crie a aba libraries.txt (botão "+" > New file) e cole o libraries.txt daqui.
//   2. Play. No Serial Monitor, cole a senha do braco-demo e tecle Enter. Ela fica só na memória da
//      simulação: projeto gratuito do Wokwi é público, então a senha NUNCA vai no código.
//      A conexão leva uns 30 s: o TLS é lento no simulador (no ESP32 de verdade, ~1 s).
//      CloudShell: aws ssm get-parameter --name /sonar/mqtt/usuarios/braco-demo --with-decryption
//                  --query Parameter.Value --output text
//   3. No notebook: .\iniciar.ps1 -Braco -Camera "http://IP_DO_CELULAR:4747/video" e mexa o letreiro
//      impresso na frente do celular: o servo pan acompanha o lado, o tilt acompanha a altura.
//   Sem câmera: gire o potenciômetro (modo manual por 10 s).
//
//   REPOUSO --(cmd ativar)--> PROCURANDO (varre de um lado para o outro)
//   PROCURANDO/REPOUSO --(mira com alvo)--> SEGUINDO
//   SEGUINDO --(alvo:false ou 3 s sem mira)--> PROCURANDO (com espera) ou REPOUSO
//   qualquer --(mexeu no potenciômetro)--> MANUAL por 10 s
#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <time.h>

// ---------------------------------------------------------------- configuração
#define SONAR_PARADA "demo"
#define MQTT_HOST "sonar.rodrigoviana.app.br"
#define MQTT_PORTA 8883  // TLS: a senha não passa aberta pelo gateway do Wokwi
#define MQTT_USUARIO "braco-demo"
#define VERSAO_FIRMWARE "0.1.0-wokwi"

const int PINO_SERVO_PAN = 18;
const int PINO_SERVO_TILT = 19;
const int PINO_POT = 34;
// A câmera fica parada (o celular), fora do braço simulado: o servo aponta direto para a posição do
// letreiro no quadro (malha aberta). No braço de verdade, com a webcam na cabeça, é malha fechada.
const float PAN_MIN = 20, PAN_MAX = 160, PAN_CENTRO = 90;
const float TILT_MIN = 60, TILT_MAX = 120, TILT_CENTRO = 90;
const float VELOCIDADE_MAX = 3.0f;        // graus por passo
const float VELOCIDADE_VARREDURA = 1.0f;  // graus por passo, procurando
const uint32_t PASSO_MS = 20, PERDEU_ALVO_MS = 3000, MANUAL_MS = 10000, STATUS_MS = 30000;

// Raízes da Let's Encrypt (ISRG Root X1 e X2), as mesmas de firmware/include/certs.h. São públicas.
static const char CA_RAIZES[] = R"PEM(
-----BEGIN CERTIFICATE-----
MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4
WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu
ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY
MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc
h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+
0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U
A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW
T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH
B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC
B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv
KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn
OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn
jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw
qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI
rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV
HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq
hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL
ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ
3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK
NFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5
ORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur
TkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC
jNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc
oyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq
4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA
mRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d
emyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIICGzCCAaGgAwIBAgIQQdKd0XLq7qeAwSxs6S+HUjAKBggqhkjOPQQDAzBPMQsw
CQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJuZXQgU2VjdXJpdHkgUmVzZWFyY2gg
R3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBYMjAeFw0yMDA5MDQwMDAwMDBaFw00
MDA5MTcxNjAwMDBaME8xCzAJBgNVBAYTAlVTMSkwJwYDVQQKEyBJbnRlcm5ldCBT
ZWN1cml0eSBSZXNlYXJjaCBHcm91cDEVMBMGA1UEAxMMSVNSRyBSb290IFgyMHYw
EAYHKoZIzj0CAQYFK4EEACIDYgAEzZvVn4CDCuwJSvMWSj5cz3es3mcFDR0HttwW
+1qLFNvicWDEukWVEYmO6gbf9yoWHKS5xcUy4APgHoIYOIvXRdgKam7mAHf7AlF9
ItgKbppbd9/w+kHsOdx1ymgHDB/qo0IwQDAOBgNVHQ8BAf8EBAMCAQYwDwYDVR0T
AQH/BAUwAwEB/zAdBgNVHQ4EFgQUfEKWrt5LSDv6kviejM9ti6lyN5UwCgYIKoZI
zj0EAwMDaAAwZQIwe3lORlCEwkSHRhtFcP9Ymd70/aTSVaYgLXTWNLxBo1BfASdW
tL4ndQavEi51mI38AjEAi/V3bNTIZargCyzuFJ0nN6T5U6VR5CmD1/iQMVtCnwr1
/q4AaOeMSQ+2b1tbFfLn
-----END CERTIFICATE-----
)PEM";

// ---------------------------------------------------------------- estado
enum class Modo : uint8_t { REPOUSO, PROCURANDO, SEGUINDO, MANUAL };

WiFiClientSecure clienteTls;
PubSubClient mqtt(clienteTls);
Servo servoPan, servoTilt;
String topicoMira, topicoCmd, topicoStatus, senha;

Modo modo = Modo::REPOUSO;
bool esperaAtiva = false, senhaPronta = false;
float pan = PAN_CENTRO, tilt = TILT_CENTRO, panAlvo = PAN_CENTRO, tiltAlvo = TILT_CENTRO;
int8_t sentidoVarredura = 1;
int potAnterior = -1;
uint32_t ultimaMiraMs = 0, manualAteMs = 0, ultimoPassoMs = 0, ultimoStatusMs = 0;
uint32_t ultimaTentativaMs = 0, ultimaTeclaMs = 0;

const char* nomeModo(Modo m) {
  switch (m) {
    case Modo::REPOUSO: return "repouso";
    case Modo::PROCURANDO: return "procurando";
    case Modo::SEGUINDO: return "seguindo";
    case Modo::MANUAL: return "manual";
  }
  return "?";
}

float limitar(float valor, float minimo, float maximo) { return valor < minimo ? minimo : valor > maximo ? maximo : valor; }

void publicarStatus() {
  ultimoStatusMs = millis();
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["online"] = true;
  doc["modo"] = nomeModo(modo);
  doc["pan"] = static_cast<int>(pan);
  doc["tilt"] = static_cast<int>(tilt);
  doc["espera"] = esperaAtiva;
  doc["versao"] = VERSAO_FIRMWARE;
  String corpo;
  serializeJson(doc, corpo);
  mqtt.publish(topicoStatus.c_str(), corpo.c_str(), true);
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

// ---------------------------------------------------------------- mensagens
void aoMirar(const JsonDocument& dados) {
  if (modo == Modo::MANUAL) return;
  if (!(dados["alvo"] | false)) {
    ir(esperaAtiva ? Modo::PROCURANDO : Modo::REPOUSO);
    return;
  }
  const float x = limitar(dados["x"] | 0.5f, 0, 1);  // centro do letreiro no quadro (0,5 = meio)
  const float y = limitar(dados["y"] | 0.5f, 0, 1);
  panAlvo = PAN_MAX - x * (PAN_MAX - PAN_MIN);
  tiltAlvo = TILT_MIN + y * (TILT_MAX - TILT_MIN);
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

void aoChegarMensagem(char* topico, uint8_t* conteudo, unsigned int tamanho) {
  JsonDocument dados;
  if (deserializeJson(dados, conteudo, tamanho)) return;
  if (topicoMira == topico) {
    aoMirar(dados);
  } else if (topicoCmd == topico) {
    aoComando(dados);
  }
}

// ---------------------------------------------------------------- rede
const char* motivoMqtt(int estado) {
  switch (estado) {
    case MQTT_CONNECTION_TIMEOUT: return "o servidor não respondeu a tempo";
    case MQTT_CONNECTION_LOST: return "a conexão caiu";
    case MQTT_CONNECT_FAILED: return "não abriu a conexão TLS (rede ou certificado; veja a linha TLS abaixo)";
    case MQTT_CONNECT_BAD_PROTOCOL: return "versão do MQTT recusada";
    case MQTT_CONNECT_BAD_CLIENT_ID: return "id de cliente recusado";
    case MQTT_CONNECT_UNAVAILABLE: return "servidor indisponível";
    case MQTT_CONNECT_BAD_CREDENTIALS: return "usuário ou senha errados";
    case MQTT_CONNECT_UNAUTHORIZED: return "não autorizado: senha errada, ou o braco-demo ainda não foi carregado no MQTT";
    default: return "desconhecido";
  }
}

void lerSenha() {
  // A senha vem do Serial Monitor (Enter, ou meio segundo sem digitar nada).
  while (Serial.available()) {
    const char c = Serial.read();
    ultimaTeclaMs = millis();
    if (c == '\n' || c == '\r') {
      if (senha.length() > 0) senhaPronta = true;
    } else {
      senha += c;
    }
  }
  if (!senhaPronta && senha.length() > 0 && millis() - ultimaTeclaMs > 500) senhaPronta = true;
  if (senhaPronta) {
    senha.trim();
    Serial.println("[rede] senha recebida, conectando ao MQTT");
  }
}

void manterConexao() {
  if (!senhaPronta) {
    lerSenha();
    return;
  }
  if (WiFi.status() != WL_CONNECTED || mqtt.connected()) return;
  const uint32_t agora = millis();
  // o TLS confere a validade do certificado: espera o relógio (NTP) ou 30 s, no pior caso
  const bool horaValida = time(nullptr) > 1700000000;
  if (agora - ultimaTentativaMs < 5000 || !(horaValida || agora > 30000)) return;
  ultimaTentativaMs = agora;
  Serial.printf("[rede] conectando a %s:%d (no simulador, o TLS leva uns 30 s)\n", MQTT_HOST, MQTT_PORTA);
  const String clienteId = String("braco-") + SONAR_PARADA;
  if (!mqtt.connect(clienteId.c_str(), MQTT_USUARIO, senha.c_str(), topicoStatus.c_str(), 1, true,
                    "{\"online\":false}")) {
    const int estado = mqtt.state();
    Serial.printf("[rede] MQTT não conectou (estado %d): %s\n", estado, motivoMqtt(estado));
    if (estado == MQTT_CONNECT_FAILED) {
      char erro[120] = "";
      const int codigo = clienteTls.lastError(erro, sizeof(erro));
      Serial.printf("[rede] TLS: %d %s | relógio: %s\n", codigo, erro,
                    time(nullptr) > 1700000000 ? "certo (NTP)" : "ainda sem NTP");
    } else if (estado == MQTT_CONNECT_BAD_CREDENTIALS || estado == MQTT_CONNECT_UNAUTHORIZED) {
      Serial.println("[rede] Para digitar a senha de novo, pare a simulação e dê play.");
    }
    return;
  }
  Serial.println("[rede] MQTT conectado: esperando a posição do letreiro");
  mqtt.subscribe(topicoMira.c_str(), 0);
  mqtt.subscribe(topicoCmd.c_str(), 1);
  publicarStatus();
}

// ---------------------------------------------------------------- servos
void lerPotenciometro() {
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
  if (modo == Modo::SEGUINDO && agora - ultimaMiraMs > PERDEU_ALVO_MS) ir(esperaAtiva ? Modo::PROCURANDO : Modo::REPOUSO);
  if (modo == Modo::PROCURANDO) {
    panAlvo = pan + sentidoVarredura * VELOCIDADE_VARREDURA;
    if (panAlvo >= PAN_MAX || panAlvo <= PAN_MIN) sentidoVarredura = -sentidoVarredura;
    panAlvo = limitar(panAlvo, PAN_MIN, PAN_MAX);
    tiltAlvo = TILT_CENTRO;
  }
  // suavização: no máximo VELOCIDADE_MAX graus por passo
  pan += limitar(panAlvo - pan, -VELOCIDADE_MAX, VELOCIDADE_MAX);
  tilt += limitar(tiltAlvo - tilt, -VELOCIDADE_MAX, VELOCIDADE_MAX);
  servoPan.write(static_cast<int>(pan + 0.5f));
  servoTilt.write(static_cast<int>(tilt + 0.5f));
}

// ---------------------------------------------------------------- Arduino
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

  WiFi.mode(WIFI_STA);
  WiFi.begin("Wokwi-GUEST", "", 6);  // a rede do simulador, com saída para a internet
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  clienteTls.setCACert(CA_RAIZES);
  mqtt.setServer(MQTT_HOST, MQTT_PORTA);
  mqtt.setCallback(aoChegarMensagem);
  mqtt.setBufferSize(1024);
  mqtt.setKeepAlive(30);
  mqtt.setSocketTimeout(15);  // o TLS é lento no simulador
  Serial.printf("[braco] Sonar Braco %s, parada %s\n", VERSAO_FIRMWARE, SONAR_PARADA);
  Serial.println("[braco] cole a senha do braco-demo aqui e tecle Enter");
}

void loop() {
  manterConexao();
  if (mqtt.connected()) mqtt.loop();
  lerPotenciometro();
  passo();
  if (millis() - ultimoStatusMs > STATUS_MS) publicarStatus();
  delay(5);  // deixa a simulação mais rápida
}
