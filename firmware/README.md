# Firmware: Sonar Ponto e Sonar Bordo

Dois ESP32 com framework Arduino, compilados pelo PlatformIO e testáveis no Wokwi antes da montagem.

| Placa | O que faz |
|---|---|
| **Sonar Ponto** | Junta a leitura do letreiro (câmera, por MQTT) com o ultrassom. Pisca o LED para o motorista enquanto há espera, apita para o usuário achar o poste e publica cada passagem com o tempo parado. |
| **Sonar Bordo** | O bipper na cabine: toca, acende o LED, mostra a parada no OLED e publica o "ciente" quando o motorista aperta o botão. |

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

O HC-SR04 vai no 5 V da placa; a versão HC-SR04P funciona em 3,3 V e dispensa o divisor.

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
| `sonar/onibus/{prefixo}/alerta` | API | `{espera_id, parada_nome, paradas_ate, linha}` |
| `sonar/onibus/{prefixo}/ciente` | Sonar Bordo | `{espera_id, horario}` |
| `sonar/onibus/{prefixo}/status` | Sonar Bordo (retido) | sinal de vida |

## Configurar e gravar

1. Instale o VS Code com a extensão PlatformIO.
2. Copie `include/secrets.example.h` para `include/secrets.h` (fora do Git) e preencha o Wi-Fi e as senhas. Cada dispositivo tem a sua, no Parameter Store:
   ```
   aws ssm get-parameter --name /sonar/mqtt/usuarios/ponto-demo --with-decryption --query Parameter.Value --output text
   aws ssm get-parameter --name /sonar/mqtt/usuarios/bordo-90001 --with-decryption --query Parameter.Value --output text
   ```
3. `pio run -e ponto -t upload` e `pio run -e bordo -t upload`. Monitor serial: `pio device monitor`.

Com a parada `demo` e o prefixo `90001`, o hardware participa do modo demonstração do app: o cenário "maquete" (`POST /api/demo/esperas` com `{"cenario":"maquete"}`) manda a previsão e o aviso, e quem confirma é o botão do Bordo e o ultrassom do Ponto.

**Calibrar o ultrassom na maquete:** o limiar padrão (150 cm) é para um ônibus de verdade. Na maquete, publique `{"acao":"config","limiar_cm":15}` em `sonar/parada/demo/cmd` (por exemplo, com o MQTT Explorer usando o usuário `sonar-api`) ou mude `LIMIAR_PADRAO_CM` em `include/config.h`.

## Wokwi

1. Instale a extensão Wokwi no VS Code.
2. Compile a versão do simulador: `pio run -e ponto_wokwi` (ou `bordo_wokwi`). Ela usa a rede `Wokwi-GUEST`.
3. Abra `wokwi/ponto/diagram.json` (ou `wokwi/bordo/diagram.json`) e clique em play. No Ponto, clique no HC-SR04 para mudar a distância e "encostar" um ônibus.

No simulador, o buzzer ativo não faz som (ele espera um sinal de frequência); acompanhe o padrão pelo monitor serial e pelo LED.

## Testes que viram cenas do vídeo

1. O ônibus certo chega e para: LED aceso, bipe longo e evento com o tempo parado.
2. O ônibus errado chega: o app diz "não é o seu".
3. O ônibus passa direto: tempo parado perto de zero, e a ocorrência aparece no app.
4. O Wi-Fi cai e volta: os eventos guardados chegam depois (veja `fila` no status).
5. A câmera desliga: o app avisa "sem confirmação visual".
