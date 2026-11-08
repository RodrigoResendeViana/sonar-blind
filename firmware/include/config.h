#pragma once
// Pinos e parâmetros. Os pinos evitam os que atrapalham o boot do ESP32 (0, 2*, 12, 15).
// *O GPIO 2 é o LED da própria placa no Bordo: só é saída depois do boot.

#define VERSAO_FIRMWARE "0.1.0"

// ---------------------------------------------------------------- Sonar Ponto
#define PINO_TRIG 26
#define PINO_ECHO 27  // pelo divisor 1 kΩ / 2 kΩ: o eco do HC-SR04 sai em 5 V
#define PINO_LED_PONTO 16
#define PINO_BUZZER_PONTO 25

// Distância (cm) abaixo da qual há um ônibus encostado no ponto. Na maquete, use ~15 cm;
// dá para mudar sem regravar: {"acao":"config","limiar_cm":15} em sonar/parada/<id>/cmd.
#define LIMIAR_PADRAO_CM 150.0f
#define HISTERESE_CM 20.0f
#define INTERVALO_LEITURA_MS 60      // o HC-SR04 pede pelo menos 60 ms entre medições
#define PRESENCA_MIN_MS 800          // perto por 0,8 s = chegou
#define AUSENCIA_MIN_MS 1500         // longe por 1,5 s = foi embora
#define PRESENCA_MAX_MS 180000UL     // nada fica "parado" mais de 3 min
#define PAROU_MIN_S 3.0f             // menos que isso conta como "passou direto"
#define LEITURA_PENDENTE_MAX_MS 8000 // leitura da câmera sem ônibus no ultrassom
#define CONFIRMACAO_MS 60000UL       // LED aceso depois do ônibus certo
#define MAX_LINHAS 8

// ---------------------------------------------------------------- Sonar Bordo
#define PINO_BUZZER_BORDO 25
#define PINO_LED_BORDO 2
#define PINO_BOTAO 33  // botão "ciente" para o GND, com pull-up interno
#define PINO_SDA 21
#define PINO_SCL 22
#define SONAR_OLED 1   // 0 se não houver display SSD1306
#define ALERTA_MAX_MS 120000UL

// ---------------------------------------------------------------- comum
#define STATUS_MS 30000UL  // sinal de vida (a API marca offline depois de 90 s sem ele)
#define TAMANHO_FILA 20    // eventos guardados enquanto o Wi-Fi está fora
