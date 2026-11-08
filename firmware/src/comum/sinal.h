#pragma once
// Toca padrões de liga/desliga num pino (LED ou buzzer ativo) sem travar o loop.
// passos = durações em ms, alternando ligado, desligado, ligado...
#include <Arduino.h>

class Sinal {
 public:
  explicit Sinal(uint8_t pino) : pino_(pino) {}

  void iniciar() {
    pinMode(pino_, OUTPUT);
    desligar();
  }

  void tocar(const uint16_t* passos, uint8_t quantidade, bool repetir) {
    passos_ = passos;
    quantidade_ = quantidade;
    repetir_ = repetir;
    indice_ = 0;
    aplicar();
  }

  void fixo() {
    passos_ = nullptr;
    digitalWrite(pino_, HIGH);
  }

  void desligar() {
    passos_ = nullptr;
    digitalWrite(pino_, LOW);
  }

  void atualizar() {
    if (passos_ == nullptr || millis() - inicio_ < passos_[indice_]) return;
    indice_++;
    if (indice_ >= quantidade_) {
      if (!repetir_) {
        desligar();
        return;
      }
      indice_ = 0;
    }
    aplicar();
  }

 private:
  void aplicar() {
    inicio_ = millis();
    digitalWrite(pino_, indice_ % 2 == 0 ? HIGH : LOW);
  }

  uint8_t pino_;
  const uint16_t* passos_ = nullptr;
  uint8_t quantidade_ = 0;
  uint8_t indice_ = 0;
  bool repetir_ = false;
  uint32_t inicio_ = 0;
};

#define TOCAR(sinal, padrao, repetir) (sinal).tocar((padrao), sizeof(padrao) / sizeof((padrao)[0]), (repetir))
