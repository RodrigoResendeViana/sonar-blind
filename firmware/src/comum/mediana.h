#pragma once
// Filtro de mediana: uma leitura absurda do ultrassom não vira "ônibus chegou".
#include <stddef.h>

template <size_t N>
class Mediana {
 public:
  void adicionar(float valor) {
    valores_[posicao_] = valor;
    posicao_ = (posicao_ + 1) % N;
    if (quantidade_ < N) quantidade_++;
  }

  bool cheia() const { return quantidade_ == N; }

  float valor() const {
    float ordenados[N];
    for (size_t i = 0; i < quantidade_; i++) ordenados[i] = valores_[i];
    for (size_t i = 1; i < quantidade_; i++) {  // insertion sort: N é pequeno
      float atual = ordenados[i];
      size_t j = i;
      while (j > 0 && ordenados[j - 1] > atual) {
        ordenados[j] = ordenados[j - 1];
        j--;
      }
      ordenados[j] = atual;
    }
    return quantidade_ ? ordenados[quantidade_ / 2] : 0.0f;
  }

 private:
  float valores_[N] = {};
  size_t posicao_ = 0;
  size_t quantidade_ = 0;
};
