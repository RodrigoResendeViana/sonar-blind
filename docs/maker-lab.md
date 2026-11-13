# Maker Lab: montagem, calibração e testes

A maquete tem um ponto de ônibus com o **Sonar Ponto** (ultrassom, LED para o motorista, buzzer para o
passageiro achar o poste), o **Sonar Braço** (cabeça pan-tilt com a webcam, que segue o letreiro) e,
dentro do "ônibus", o **Sonar Bordo** (bipper do motorista). O notebook do ponto roda o serviço da
câmera. Tudo conversa com a nuvem pelo MQTT com TLS.

```
                    ┌──────────────── EC2 (API, MQTT 8883, IA, n8n) ────────────────┐
                    │                                                                │
  notebook ──USB── webcam (na cabeça pan-tilt)                                       │
     │  serviço da câmera: lê o letreiro e publica visao (linha) e mira (posição) ──┤
     │                                                                               │
  Sonar Ponto (ESP32): ultrassom + LED + buzzer ◀── cmd ───────────────────────────┤
  Sonar Braço (ESP32): 2 servos ◀── mira (~7/s) ───────────────────────────────────┤
  Sonar Bordo (ESP32): buzzer + LED + OLED + botão ◀── alerta / ciente ──▶ ───────┘
```

Pinos e tópicos: [`firmware/README.md`](../firmware/README.md). Contratos: [`contratos.md`](contratos.md).

## 1. Material

| Qtd | Item | Para quê | Observação |
|---|---|---|---|
| 2–3 | ESP32 DevKit (38 pinos) | Ponto, Braço e Bordo | com 2 placas, o Bordo pode ficar só no Wokwi |
| 2 | Servo SG90 (ou MG90S, engrenagem de metal) | pan e tilt | MG90S treme menos com a webcam |
| 1 | Suporte pan-tilt para micro servo | cabeça | impresso em 3D ou de acrílico |
| 1 | Fonte 5 V / 2 A (ou carregador USB com cabo cortado) | servos | **nunca** o 5 V do ESP32 |
| 1 | Webcam USB pequena | câmera na cabeça | quanto mais leve, melhor |
| 1 | Sensor ultrassônico HC-SR04 (ou HC-SR04P) | detectar o ônibus | o HC-SR04 precisa do divisor 1 kΩ / 2 kΩ no ECHO |
| 1 | LED de alto brilho + resistor 220 Ω | aviso ao motorista | |
| 2 | Buzzer ativo 5 V | Ponto e Bordo | |
| 1 | Display OLED SSD1306 128x64 (I²C) | Bordo | opcional |
| 1 | Botão táctil | "ciente" do motorista no Bordo | |
| 1 | Potenciômetro 10 kΩ | modo manual do braço | opcional (`USAR_POT 0` se não usar) |
| 1 | Botão grande (de preferência com relevo) | "tem passageiro" no poste do Sonar Ponto | GPIO 32 e GND |
| 1 | ESP32-CAM AI-Thinker + adaptador USB-serial (FTDI 3,3 V) | câmera sem fio na cabeça do braço | opcional: substitui a webcam USB |
| — | Protoboards, jumpers, capacitor 470–1000 µF / 10 V | | capacitor na entrada dos servos evita resets |
| — | Papelão, cola quente, letreiros impressos | maquete | `python visao/imprimir.py` |

## 2. Simular antes de montar (Wokwi)

1. VS Code + extensões PlatformIO e Wokwi.
2. `cd firmware`, copie `include/secrets.example.h` para `include/secrets.h` (o Wokwi usa a rede
   `Wokwi-GUEST`; preencha só as senhas do MQTT).
3. Braço: `pio run -e braco_wokwi`, abra `wokwi/braco/diagram.json`, play. Gire o potenciômetro: os
   servos acompanham (modo manual). Com o serviço da câmera em modo teclado no notebook
   (`.\iniciar.ps1 -Modo teclado -Braco`), digite `DEMO-10@0.1` e `DEMO-10@0.9`: o servo pan vira.
4. Ponto e Bordo: `pio run -e ponto_wokwi` / `bordo_wokwi`, com os diagramas das pastas `wokwi/ponto`
   e `wokwi/bordo`.
5. **Grave a tela**: é a primeira evidência da matéria.

## 3. Montar

### Sonar Braço

1. **Centre os servos antes de prender os braços**: grave o firmware e ligue; ele coloca os dois em
   90°. Só então encaixe os braços do servo no suporte, com a cabeça olhando para a frente.
2. Servo pan (base) no GPIO 18, servo tilt no GPIO 19 (fio laranja/amarelo = sinal).
3. Fio vermelho dos dois servos no **+5 V da fonte externa**; marrom/preto no GND da fonte;
   **GND da fonte ligado ao GND do ESP32** (sem isso o sinal não tem referência).
4. Capacitor eletrolítico entre +5 V e GND, perto dos servos (polaridade!).
5. Potenciômetro: pontas em 3V3 e GND, cursor no GPIO 34.
6. Prenda a webcam na cabeça com fita dupla face/abraçadeira; deixe folga no cabo USB para a cabeça
   girar de 20° a 160° sem puxar.

### Sonar Ponto

HC-SR04 com TRIG no GPIO 26 e ECHO no GPIO 27 **pelo divisor** (ECHO → 1 kΩ → GPIO 27 → 2 kΩ → GND),
LED (com 220 Ω) no GPIO 16, buzzer no GPIO 25. O sensor fica na altura do "ônibus", virado para a rua.

**Botão do poste** entre o GPIO 32 e o GND (o pull-up é interno). Ele é a saída para quem está sem o
app ou sem internet: um toque e o ponto dá três bips curtos ("recebi"), o LED começa a piscar para os
motoristas na hora (mesmo sem rede, por 10 minutos) e, com rede, a API avisa o Sonar Bordo de todos
os ônibus que vêm para o ponto. O motorista para e fala a linha. Cole uma etiqueta em braille ou em
relevo no botão, na altura da mão.

### Sonar Câmera (opcional: ESP32-CAM sem fio)

A ESP32-CAM vai na cabeça do braço no lugar da webcam, sem cabo USB até o notebook. Ela só transmite
o vídeo pela rede local (MJPEG, com token na URL); o notebook continua fazendo o OCR/YOLO, porque um
ESP32 não roda visão computacional desse porte.

1. Em `firmware/include/secrets.h`, defina `CAMERA_TOKEN` (um texto aleatório) e o Wi-Fi (o mesmo
   do notebook).
2. Gravação: ESP32-CAM no adaptador USB-serial (5V→5V, GND→GND, U0T→RX, U0R→TX) e **IO0 ligado ao
   GND**; `pio run -e camera -t upload`; tire o IO0 do GND e aperte RESET.
3. O monitor serial mostra o endereço: `http://192.168.x.y:81/stream?t=<token>`.
4. No notebook: `.\iniciar.ps1 -Braco -Camera "http://192.168.x.y:81/stream?t=<token>"`.
5. Alimente com 5 V e 2 A (a câmera e o Wi-Fi puxam picos); se a imagem vier de cabeça para baixo,
   `CAMERA_VIRAR 1`.

### Sonar Bordo

Buzzer no GPIO 25, botão entre o GPIO 33 e o GND, OLED com SDA no 21 e SCL no 22. Vai dentro ou em
cima do ônibus de papelão.

## 4. Gravar

1. Senhas do MQTT (CloudShell; os usuários existem depois do `terraform apply`):
   ```bash
   for u in ponto-demo braco-demo bordo-90001 camera-demo; do
     echo -n "$u: "; aws ssm get-parameter --name /sonar/mqtt/usuarios/$u --with-decryption --query Parameter.Value --output text
   done
   ```
2. Preencha `firmware/include/secrets.h` (Wi-Fi e senhas). Esse arquivo não vai para o Git; num
   computador da faculdade, apague depois de gravar.
3. `pio run -e braco -t upload`, `pio run -e ponto -t upload`, `pio run -e bordo -t upload`.
4. `pio device monitor`: cada placa mostra a conexão com o Wi-Fi e com o MQTT; o braço também mostra
   `[braco] repouso -> procurando` a cada mudança de modo.

## 5. Calibrar o braço

Rode o serviço da câmera com a janela e a mira sempre ligada:

```powershell
cd edge
.\iniciar.ps1 -Braco
```

Segure um letreiro impresso na frente da câmera e mova devagar para os lados. Ajuste em
`firmware/include/config.h` e grave de novo:

| Sintoma | Ajuste |
|---|---|
| Vira para o lado **contrário** ao letreiro | inverta o sinal: `GANHO_PAN -40.0f` (e/ou `GANHO_TILT`) |
| Treme parado com o letreiro no meio | aumente `ZONA_MORTA` (0.06 → 0.10) |
| Lento para alcançar o letreiro | aumente `GANHO_PAN` (40 → 55) ou `VELOCIDADE_MAX` (3 → 5) |
| Passa do ponto e volta (oscila) | diminua `GANHO_PAN` (40 → 25) |
| Bate no fim do curso / puxa o cabo | ajuste `PAN_MIN`/`PAN_MAX` e `TILT_MIN`/`TILT_MAX` |
| ESP32 reinicia quando o servo mexe | fonte fraca ou GND não comum; capacitor na entrada dos servos |
| Câmera fixa ao lado, não na cabeça | `CAMERA_NO_BRACO 0`: o braço só aponta para onde o letreiro está |

Na maquete, ajuste também o ultrassom: `LIMIAR_PADRAO_CM 15` em `config.h` (o padrão, 150 cm, é
para ônibus de verdade).

## 6. Testar (cada teste vira uma cena do vídeo)

1. **Wokwi**: braço no modo manual e seguindo `DEMO-10@x` pelo teclado.
2. **Bancada**: cada placa conecta no Wi-Fi e no MQTT (monitor serial).
3. **Braço seguindo**: letreiro impresso andando na frente da webcam; a cabeça acompanha.
4. **Procura**: com uma espera aberta no app e nenhum letreiro, a cabeça varre de um lado para o outro.
5. **Jornada completa** (cenário "maquete" do app): o passageiro pede a linha → LED do ponto pisca e o
   Bordo toca → o motorista aperta "ciente" → o ônibus de papelão chega → o braço segue o letreiro e a
   câmera lê a linha → "é o seu" (LED aceso + bipe longo).
6. **Falhas**: tire o Wi-Fi do Ponto e devolva (os eventos chegam depois); desligue a câmera (o app
   avisa "sem confirmação visual").

## 7. Evidências para o relatório

- Esquema elétrico (print do Wokwi de cada placa) e a tabela de ligações.
- Lista de materiais com o custo que vocês pagaram.
- Fotos da montagem (cabeça pan-tilt, ponto, ônibus) e da maquete inteira.
- Vídeo do Wokwi e vídeo do braço seguindo o letreiro (com a janela da câmera aparecendo).
- A máquina de estados do braço e do Ponto (`firmware/README.md`) e a tabela de calibração final.
