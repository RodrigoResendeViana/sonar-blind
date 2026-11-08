#pragma once
// O display SSD1306 só tem ASCII: troca as letras acentuadas (UTF-8) pela letra sem acento.
#include <Arduino.h>

inline char semAcento(uint8_t segundo) {
  if (segundo >= 0x80 && segundo <= 0x85) return 'A';
  if (segundo == 0x87) return 'C';
  if (segundo >= 0x88 && segundo <= 0x8B) return 'E';
  if (segundo >= 0x8C && segundo <= 0x8F) return 'I';
  if (segundo == 0x91) return 'N';
  if (segundo >= 0x92 && segundo <= 0x96) return 'O';
  if (segundo >= 0x99 && segundo <= 0x9C) return 'U';
  if (segundo >= 0xA0 && segundo <= 0xA5) return 'a';
  if (segundo == 0xA7) return 'c';
  if (segundo >= 0xA8 && segundo <= 0xAB) return 'e';
  if (segundo >= 0xAC && segundo <= 0xAF) return 'i';
  if (segundo == 0xB1) return 'n';
  if (segundo >= 0xB2 && segundo <= 0xB6) return 'o';
  if (segundo >= 0xB9 && segundo <= 0xBC) return 'u';
  return '?';
}

inline String paraAscii(const String& entrada) {
  String saida;
  for (unsigned int i = 0; i < entrada.length(); i++) {
    const uint8_t c = static_cast<uint8_t>(entrada[i]);
    if (c < 0x80) {
      saida += static_cast<char>(c);
    } else if (c == 0xC3 && i + 1 < entrada.length()) {
      saida += semAcento(static_cast<uint8_t>(entrada[++i]));
    } else if ((c & 0xC0) != 0x80) {
      saida += '?';  // outro caractere de vários bytes
    }
  }
  return saida;
}
