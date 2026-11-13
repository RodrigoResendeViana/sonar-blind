// Sonar Câmera: ESP32-CAM (AI-Thinker) presa na cabeça do Sonar Braço, mandando o vídeo sem fio
// para o notebook do ponto. Quem acha e lê o letreiro continua sendo o notebook (OCR/YOLO não cabem
// no ESP32); a câmera só transmite, e só para quem tem o token.
//
//   notebook: python -m sonar_camera --modo webcam --camera "http://<ip>:81/stream?t=<token>"
//
// O vídeo fica na rede local (nada vai para a nuvem). Sem o token na URL, a câmera responde 403.
#include <Arduino.h>
#include <ESPmDNS.h>
#include <WiFi.h>

#include "esp_camera.h"
#include "esp_http_server.h"
#include "secrets.h"

#ifndef CAMERA_TOKEN
#error "defina CAMERA_TOKEN em include/secrets.h"
#endif

namespace {

// pinos da placa AI-Thinker ESP32-CAM
constexpr int PWDN = 32, RESET = -1, XCLK = 0, SIOD = 26, SIOC = 27;
constexpr int Y9 = 35, Y8 = 34, Y7 = 39, Y6 = 36, Y5 = 21, Y4 = 19, Y3 = 18, Y2 = 5;
constexpr int VSYNC = 25, HREF = 23, PCLK = 22;
constexpr int LED_FLASH = 4;

#define LIMITE "sonarquadro7f3a9c"
const char* TIPO_STREAM = "multipart/x-mixed-replace;boundary=" LIMITE;
const char* SEPARADOR = "\r\n--" LIMITE "\r\n";
const char* CABECALHO_PARTE = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

httpd_handle_t servidor = nullptr;

bool tokenValido(httpd_req_t* req) {
  char consulta[128];
  char token[64];
  if (httpd_req_get_url_query_str(req, consulta, sizeof consulta) != ESP_OK) return false;
  if (httpd_query_key_value(consulta, "t", token, sizeof token) != ESP_OK) return false;
  return strcmp(token, CAMERA_TOKEN) == 0;
}

esp_err_t negar(httpd_req_t* req) {
  httpd_resp_set_status(req, "403 Forbidden");
  return httpd_resp_send(req, "token invalido", HTTPD_RESP_USE_STRLEN);
}

esp_err_t transmitir(httpd_req_t* req) {
  if (!tokenValido(req)) return negar(req);
  httpd_resp_set_type(req, TIPO_STREAM);
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  Serial.println("[camera] notebook conectado");
  esp_err_t resultado = ESP_OK;
  while (resultado == ESP_OK) {
    camera_fb_t* quadro = esp_camera_fb_get();
    if (quadro == nullptr) {
      Serial.println("[camera] falha ao capturar o quadro");
      resultado = ESP_FAIL;
      break;
    }
    char cabecalho[96];
    const int tamanho = snprintf(cabecalho, sizeof cabecalho, CABECALHO_PARTE, static_cast<unsigned>(quadro->len));
    resultado = httpd_resp_send_chunk(req, SEPARADOR, strlen(SEPARADOR));
    if (resultado == ESP_OK) resultado = httpd_resp_send_chunk(req, cabecalho, tamanho);
    if (resultado == ESP_OK) {
      resultado = httpd_resp_send_chunk(req, reinterpret_cast<const char*>(quadro->buf), quadro->len);
    }
    esp_camera_fb_return(quadro);
  }
  Serial.println("[camera] notebook desconectado");
  return resultado;
}

esp_err_t foto(httpd_req_t* req) {
  if (!tokenValido(req)) return negar(req);
  camera_fb_t* quadro = esp_camera_fb_get();
  if (quadro == nullptr) {
    httpd_resp_set_status(req, "503 Service Unavailable");
    return httpd_resp_send(req, "sem quadro", HTTPD_RESP_USE_STRLEN);
  }
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  const esp_err_t resultado = httpd_resp_send(req, reinterpret_cast<const char*>(quadro->buf), quadro->len);
  esp_camera_fb_return(quadro);
  return resultado;
}

esp_err_t saude(httpd_req_t* req) {
  httpd_resp_set_type(req, "text/plain");
  return httpd_resp_send(req, "Sonar Camera: ok", HTTPD_RESP_USE_STRLEN);
}

bool iniciarCamera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2;
  config.pin_d1 = Y3;
  config.pin_d2 = Y4;
  config.pin_d3 = Y5;
  config.pin_d4 = Y6;
  config.pin_d5 = Y7;
  config.pin_d6 = Y8;
  config.pin_d7 = Y9;
  config.pin_xclk = XCLK;
  config.pin_pclk = PCLK;
  config.pin_vsync = VSYNC;
  config.pin_href = HREF;
  config.pin_sccb_sda = SIOD;
  config.pin_sccb_scl = SIOC;
  config.pin_pwdn = PWDN;
  config.pin_reset = RESET;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  // VGA (640x480) é o bastante para o OCR do letreiro e cabe no Wi-Fi a ~10 quadros/s
  config.frame_size = psramFound() ? FRAMESIZE_VGA : FRAMESIZE_QVGA;
  config.jpeg_quality = 12;
  config.fb_count = psramFound() ? 2 : 1;
  config.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  config.grab_mode = CAMERA_GRAB_LATEST;  // sempre o quadro mais novo (o braço segue o letreiro)
  if (esp_camera_init(&config) != ESP_OK) return false;
  sensor_t* sensor = esp_camera_sensor_get();
  if (sensor != nullptr) {
    sensor->set_vflip(sensor, CAMERA_VIRAR);    // conforme a câmera foi presa na cabeça
    sensor->set_hmirror(sensor, CAMERA_VIRAR);
  }
  return true;
}

void iniciarServidor() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 81;
  config.ctrl_port = 32769;
  const httpd_uri_t rotas[] = {
      {"/stream", HTTP_GET, transmitir, nullptr},
      {"/foto", HTTP_GET, foto, nullptr},
      {"/", HTTP_GET, saude, nullptr},
  };
  if (httpd_start(&servidor, &config) != ESP_OK) {
    Serial.println("[camera] não consegui abrir o servidor");
    return;
  }
  for (const httpd_uri_t& rota : rotas) httpd_register_uri_handler(servidor, &rota);
}

}  // namespace

void setup() {
  Serial.begin(115200);
  pinMode(LED_FLASH, OUTPUT);
  digitalWrite(LED_FLASH, LOW);  // o flash fica desligado: ofusca e chama atenção à toa
  if (!iniciarCamera()) {
    Serial.println("[camera] câmera não encontrada: confira o cabo flat e a alimentação (5 V, 2 A)");
    delay(5000);
    ESP.restart();
  }
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // sem economia de energia: o vídeo não engasga
  WiFi.begin(WIFI_SSID, WIFI_SENHA);
  Serial.print("[camera] conectando ao Wi-Fi");
  for (int tentativa = 0; WiFi.status() != WL_CONNECTED; tentativa++) {
    delay(500);
    Serial.print(".");
    if (tentativa > 60) ESP.restart();
  }
  if (MDNS.begin("sonar-camera")) MDNS.addService("http", "tcp", 81);
  iniciarServidor();
  Serial.printf("\n[camera] pronta: http://%s:81/stream?t=<token> (ou http://sonar-camera.local:81/...)\n",
                WiFi.localIP().toString().c_str());
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[camera] Wi-Fi caiu; reconectando");
    WiFi.reconnect();
    delay(3000);
  }
  delay(1000);
}
