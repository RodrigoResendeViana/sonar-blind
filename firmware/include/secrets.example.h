#pragma once
// Copie para secrets.h (que fica fora do Git) e preencha.
// A senha de cada dispositivo está no Parameter Store da AWS (rode no CloudShell):
//   aws ssm get-parameter --name /sonar/mqtt/usuarios/ponto-demo --with-decryption --query Parameter.Value --output text

// Wi-Fi (no Wokwi, o firmware usa a rede Wokwi-GUEST e ignora estes dois)
#define WIFI_SSID "nome-da-rede"
#define WIFI_SENHA "senha-da-rede"

// Broker MQTT da EC2: TLS na porta 8883
#define MQTT_HOST "sonar.rodrigoviana.app.br"
#define MQTT_PORTA 8883
#define MQTT_TLS 1

// Sonar Ponto: a parada "demo" participa do modo demonstração do app
#define SONAR_PARADA "demo"
#define MQTT_USUARIO_PONTO "ponto-demo"
#define MQTT_SENHA_PONTO "cole-a-senha-do-parameter-store"

// Sonar Bordo: o prefixo 90001 é o ônibus da demonstração
#define SONAR_PREFIXO "90001"
#define MQTT_USUARIO_BORDO "bordo-90001"
#define MQTT_SENHA_BORDO "cole-a-senha-do-parameter-store"

// Sonar Braço (Maker Lab): mesma parada do Sonar Ponto
#define MQTT_USUARIO_BRACO "braco-demo"
#define MQTT_SENHA_BRACO "cole-a-senha-do-parameter-store"

// Sonar Câmera (ESP32-CAM na cabeça do braço): token que o notebook põe na URL do vídeo.
// Troque por um texto aleatório (ex.: python -c "import secrets; print(secrets.token_urlsafe(16))").
#define CAMERA_TOKEN "troque-por-um-texto-aleatorio"
#define CAMERA_VIRAR 0  // 1 se a imagem aparecer de cabeça para baixo
