# Firmware: Sonar Ponto, Sonar Bordo e Sonar Braço

Três ESP32 com framework Arduino, compilados pelo PlatformIO e testáveis no Wokwi antes da montagem.

| Placa | O que faz |
|---|---|
| **Sonar Ponto** | Junta a leitura do letreiro (câmera, por MQTT) com o ultrassom. Pisca o LED para o motorista enquanto há espera, apita para o usuário achar o poste e publica cada passagem com o tempo parado. |
| **Sonar Bordo** | O bipper na cabine: toca, acende o LED, mostra a parada no OLED e publica o "ciente" quando o motorista aperta o botão. |
| **Sonar Braço** (Maker Lab) | Cabeça pan-tilt com 2 servos que segue o letreiro: recebe do serviço da câmera a posição do letreiro no quadro e gira para mantê-lo no centro. Varre de um lado para o outro enquanto há espera e nenhum letreiro à vista. |

## Ligações

| Placa | Componente | Pino do ESP32 |
|---|---|---|
| Ponto | HC-SR04 TRIG | GPIO 26 |
| Ponto | HC-SR04 ECHO, **pelo divisor 1 kΩ / 2 kΩ** (o eco sai em 5 V) | GPIO 27 |
| Ponto | LED de alto brilho (com resistor de 220 Ω) | GPIO 16 |
| Ponto | Buzzer ativo | GPIO 25 |
| Bordo | Buzzer ativo | GPIO 25 |
| Bordo | LED | GPIO 2 (LED da placa) |
| Bordo | Botão "ciente" para o GND (pull-up interno) | GPIO 33 |
| Bordo | OLED SSD1306 SDA / SCL | GPIO 21 / 22 |
| Braço | Servo pan (sinal) | GPIO 18 |
| Braço | Servo tilt (sinal) | GPIO 19 |
| Braço | Potenciômetro 10 kΩ (cursor; pontas em 3V3 e GND) | GPIO 34 |
| Braço | Servos: V+ na **fonte de 5 V externa** (2 A), GND da fonte ligado ao GND do ESP32 | — |

O HC-SR04 vai no 5 V da placa; a versão HC-SR04P funciona em 3,3 V e dispensa o divisor.

Não alimente os servos pelo 5 V do ESP32: o pico de corrente reinicia a placa.

## Sonar Braço (Maker Lab)

Material: ESP32 DevKit, 2 servos SG90 ou MG90S, suporte pan-tilt, fonte 5 V / 2 A, potenciômetro
10 kΩ (opcional) e uma webcam USB presa na cabeça, ligada ao notebook.

```
webcam ──USB──▶ notebook: YOLO acha o letreiro ──MQTT sonar/parada/demo/mira {x, y}──▶ ESP32 ──PWM──▶ servos
```

O ESP32 não roda visão computacional: o notebook acha e lê o letreiro (OCR, ou YOLO + OCR quando o
modelo existir), rastreia entre uma leitura e outra (`edge/`) e manda só a posição.
Com `CAMERA_NO_BRACO 1` (padrão), a câmera gira junto e o braço corrige até o letreiro ficar no
meio do quadro (controle proporcional com zona morta e velocidade limitada). Com `0`, a câmera fica
parada e o braço só aponta para onde o letreiro está. Ganhos e limites ficam em `include/config.h`.

```
REPOUSO ──cmd "ativar"──▶ PROCURANDO (varre de 20° a 160°)
PROCURANDO/REPOUSO ──mira com alvo──▶ SEGUINDO
SEGUINDO ──{"alvo":false} ou 3 s sem mira──▶ PROCURANDO (com espera) ou REPOUSO
qualquer ──girou o potenciômetro──▶ MANUAL por 10 s
```

Testar sem câmera: `python -m sonar_camera --parada demo --linhas DEMO-10 --mirar-sempre` e digite
`DEMO-10@0.1`, `DEMO-10@0.9`... para mover o letreiro "virtual" da esquerda para a direita.
No Wokwi (`pio run -e braco_wokwi`, abra `wokwi/braco/diagram.json`), gire o potenciômetro.

## Máquina de estados do Sonar Ponto

```
OCIOSO ──cmd "ativar"──▶ AGUARDANDO (LED pulsando, 3 bipes de localização)
AGUARDANDO ──ultrassom: algo a menos de 150 cm por 0,8 s──▶ ONIBUS_DETECTADO
ONIBUS_DETECTADO ──câmera leu uma linha esperada──▶ LED aceso + bipe longo ("é o seu")
ONIBUS_DETECTADO ──longe por 1,5 s──▶ publica a passagem (linha, confiança, tempo parado)
    linha certa ──▶ AGUARDANDO_CONFIRMACAO (LED aceso por 1 min)
    outra linha ──▶ AGUARDANDO
o usuário confirma o embarque, ou diz que o ônibus não parou, no app ──▶ a API manda "desativar" ──▶ OCIOSO
```

Falhas previstas: Wi-Fi fora (LED em pisca duplo e até 20 eventos guardados, que saem quando a conexão volta), câmera fora (a passagem sai com `camera_ok: false` e o app avisa "sem confirmação visual"), leitura absurda do sensor (filtro de mediana de 5 leituras), comando retido de uma espera vencida (ignorado pelo `expira_em`).

## Tópicos MQTT

O contrato completo está em [`docs/contratos.md`](../docs/contratos.md).

| Tópico | Quem publica | Conteúdo |
|---|---|---|
| `sonar/parada/{id}/cmd` | API (retido) | `ativar` (espera_id, linhas_alvo, expira_em), `desativar`, `localizar`, `config` (limiar_cm) |
| `sonar/parada/{id}/visao` | serviço da câmera | `{linha_lida, confianca, passou_em}` |
| `sonar/parada/{id}/evento` | Sonar Ponto | `{espera_id, linha_lida, confianca, passou_em, tempo_parado_s, parou, camera_ok}` |
| `sonar/parada/{id}/status` | Sonar Ponto (retido, a cada 30 s) | `{online, estado, rssi, uptime_s, fila, camera_ok}`; se a conexão cair, o broker publica `{online:false}` |
| `sonar/parada/{id}/mira` | serviço da câmera (até ~7/s) | `{alvo, x, y, linha}` ou `{alvo:false}` |
| `sonar/parada/{id}/braco/status` | Sonar Braço (retido) | `{online, modo, pan, tilt, espera}` |
| `sonar/onibus/{prefixo}/alerta` | API | `{espera_id, parada_nome, paradas_ate, linha}` |
| `sonar/onibus/{prefixo}/ciente` | Sonar Bordo | `{espera_id, horario}` |
| `sonar/onibus/{prefixo}/status` | Sonar Bordo (retido) | sinal de vida |

O passo a passo da montagem, a lista de materiais e a calibração estão em
[`docs/maker-lab.md`](../docs/maker-lab.md).

## Configurar e gravar

1. Instale o VS Code com a extensão PlatformIO.
2. Copie `include/secrets.example.h` para `include/secrets.h` (fora do Git) e preencha o Wi-Fi e as senhas. Cada dispositivo tem a sua, no Parameter Store:
   ```
   aws ssm get-parameter --name /sonar/mqtt/usuarios/ponto-demo --with-decryption --query Parameter.Value --output text
   aws ssm get-parameter --name /sonar/mqtt/usuarios/bordo-90001 --with-decryption --query Parameter.Value --output text
   aws ssm get-parameter --name /sonar/mqtt/usuarios/braco-demo --with-decryption --query Parameter.Value --output text
   ```
3. `pio run -e ponto -t upload`, `pio run -e bordo -t upload` e `pio run -e braco -t upload`. Monitor serial: `pio device monitor`.

Com a parada `demo` e o prefixo `90001`, o hardware participa do modo demonstração do app: o cenário "maquete" (`POST /api/demo/esperas` com `{"cenario":"maquete"}`) manda a previsão e o aviso, e quem confirma é o botão do Bordo e o ultrassom do Ponto.

**Calibrar o ultrassom na maquete:** o limiar padrão (150 cm) é para um ônibus de verdade. Na maquete, publique `{"acao":"config","limiar_cm":15}` em `sonar/parada/demo/cmd` (por exemplo, com o MQTT Explorer usando o usuário `sonar-api`) ou mude `LIMIAR_PADRAO_CM` em `include/config.h`.

## Wokwi

1. Instale a extensão Wokwi no VS Code.
2. Compile a versão do simulador: `pio run -e ponto_wokwi` (ou `bordo_wokwi`, `braco_wokwi`). Ela usa a rede `Wokwi-GUEST`.
3. Abra `wokwi/ponto/diagram.json` (ou `wokwi/bordo/diagram.json`, `wokwi/braco/diagram.json`) e clique em play. No Ponto, clique no HC-SR04 para mudar a distância e "encostar" um ônibus.

No simulador, o buzzer ativo não faz som (ele espera um sinal de frequência); acompanhe o padrão pelo monitor serial e pelo LED.

## Testes que viram cenas do vídeo

1. O ônibus certo chega e para: LED aceso, bipe longo e evento com o tempo parado.
2. O ônibus errado chega: o app diz "não é o seu".
3. O ônibus passa direto: tempo parado perto de zero, e a ocorrência aparece no app.
4. O Wi-Fi cai e volta: os eventos guardados chegam depois (veja `fila` no status).
5. A câmera desliga: o app avisa "sem confirmação visual".
