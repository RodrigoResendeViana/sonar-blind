# Sonar — Maker Lab

**FIAP · Global Solution 2026.2 · CitizenTech**
Grupo: [PREENCHER] · Integrantes (RM): [PREENCHER]
Repositório: https://github.com/RodrigoResendeViana/sonar-blind · Vídeo: [PREENCHER: link]

## 1. Problema

No ponto, a pessoa cega não sabe qual ônibus está chegando e o motorista não sabe que alguém precisa
dele. Faltam dois sinais físicos: um que **aponte e acompanhe** o ônibus que chega (para a câmera ler
o letreiro) e outro que **avise o motorista** de forma inequívoca.

## 2. Solução

Três dispositivos ESP32 ligados à nuvem por MQTT com TLS:

| Dispositivo | O que faz | Componentes |
|---|---|---|
| **Sonar Braço** | cabeça pan-tilt com a webcam que **segue o letreiro** do ônibus; varre o horizonte enquanto ninguém aparece | ESP32, 2 servos, suporte pan-tilt, fonte 5 V, potenciômetro |
| **Sonar Ponto** | detecta o ônibus parando (ultrassom), pisca um LED para o motorista e apita para o passageiro achar o poste | ESP32, HC-SR04, LED de alto brilho, buzzer |
| **Sonar Bordo** | bipper na cabine: avisa o motorista que há um passageiro cego no próximo ponto; botão "ciente" | ESP32, buzzer, LED, OLED, botão |

O braço é integrado à visão computacional: o notebook acha e lê o letreiro e publica a posição dele
no quadro (`sonar/parada/demo/mira`, ~7 vezes por segundo); o ESP32 move os servos para manter o
letreiro no centro.

## 3. Controle do braço

- **Malha fechada** (câmera na cabeça): erro = posição do letreiro − centro do quadro; correção
  proporcional (`GANHO_PAN`), zona morta para não tremer e velocidade limitada por passo (sem tranco
  na fonte).
- **Máquina de estados**: REPOUSO → PROCURANDO (varredura) → SEGUINDO → (perdeu por 3 s) →
  PROCURANDO; MANUAL pelo potenciômetro por 10 s (demonstração sem câmera).
- **Robustez**: o rastreador do notebook dá a posição entre uma leitura e outra do OCR; "alvo:false"
  quando o letreiro some; o braço volta a procurar sozinho.

[PRINT: diagrama do Wokwi do braço] [PRINT: foto da cabeça pan-tilt montada]

## 4. Materiais e ligações

[PREENCHER: tabela de materiais com o custo pago — base em `docs/maker-lab.md`, seção 1]

[PRINT: esquema elétrico / Wokwi de cada placa]

Pinos: servo pan GPIO 18, servo tilt GPIO 19, potenciômetro GPIO 34; servos na fonte de 5 V externa
com GND comum. Ponto e Bordo: `firmware/README.md`.

## 5. Calibração e testes

| Parâmetro | Valor final | Por quê |
|---|---|---|
| `GANHO_PAN` | [PREENCHER] | |
| `ZONA_MORTA` | [PREENCHER] | |
| `VELOCIDADE_MAX` | [PREENCHER] | |
| `LIMIAR_PADRAO_CM` (ultrassom) | [PREENCHER] | maquete |

| Teste | Resultado |
|---|---|
| Wokwi: modo manual e seguindo pelo teclado | [PREENCHER] |
| Braço seguindo letreiro impresso andando | [PREENCHER: segue até X cm/s] |
| Varredura com espera aberta | [PREENCHER] |
| Jornada completa na maquete | [PREENCHER] |
| Wi-Fi cai e volta (eventos guardados) | [PREENCHER] |

[PRINT: fotos da maquete] [VÍDEO: braço seguindo o letreiro, com a janela da câmera]

## 6. Decisões

- **Visão no notebook, controle no ESP32**: o ESP32 não roda YOLO/OCR; recebe só dois números (x, y).
- **Pan-tilt com 2 servos** em vez de braço com mais juntas: mesmo efeito (seguir o ônibus) com menos
  peso, custo e pontos de falha.
- **Fonte externa para os servos**: o pico de corrente dos servos reinicia o ESP32 se dividir o 5 V.
- **Segurança**: senha e ACL por dispositivo no MQTT (o braço só lê `mira` e `cmd`), TLS com as raízes
  da Let's Encrypt fixadas no firmware.

## 7. Como testar

Wokwi: `pio run -e braco_wokwi` e `firmware/wokwi/braco/diagram.json`. Montagem e calibração:
`docs/maker-lab.md`.
