# Serviço da câmera do Sonar Ponto

Roda no notebook do ponto. Lê a webcam **só enquanto há uma espera ativa**, acha o letreiro com
o YOLO da equipe de Visão, lê o texto com OCR, casa com o vocabulário restrito da parada, confirma
depois de 3 quadros seguidos iguais e publica só o texto em `sonar/parada/{id}/visao`:

```json
{"linha_lida": "DEMO-10", "confianca": 0.91, "passou_em": "2026-11-12T13:05:00Z"}
```

Nenhuma imagem sai do notebook. O Sonar Ponto (ESP32) junta essa leitura com o ultrassom e decide.
Sem o Sonar Ponto, a câmera decide sozinha (`--sem-ponto`, veja abaixo).

Em paralelo, a cada quadro com letreiro, publica a posição dele em `sonar/parada/{id}/mira`
(até ~7 vezes por segundo) para o **Sonar Braço** (Maker Lab) girar a câmera e seguir o ônibus:

```json
{"alvo": true, "x": 0.42, "y": 0.5, "linha": "DEMO-10"}
```

Prioridade do alvo: o ônibus esperado, depois qualquer linha conhecida, depois qualquer letreiro.
Quando o letreiro some por 1 s, publica `{"alvo": false}`. Com `--mirar-sempre`, a mira funciona
mesmo sem espera aberta (para a demonstração do braço).

## Como acha o letreiro

| `--detector` | O que faz | Precisa de modelo? |
|---|---|---|
| `auto` (padrão) | YOLO se `modelos/letreiro.pt` existir; senão, só OCR | não |
| `ocr` | o EasyOCR acha e lê os textos do quadro inteiro | não: já funciona com letreiro impresso |
| `yolo` | o modelo da equipe de Visão acha o letreiro; o OCR lê só o recorte | sim (`visao/treinar.py`) |

A câmera roda em segundo plano: um fio captura os quadros e **rastreia** o letreiro (correlação,
milissegundos por quadro); outro roda o OCR/YOLO no quadro mais recente. Assim a posição para o
braço sai a ~7 por segundo mesmo com o OCR levando ~1 s. A posição rastreada vai para a mira, mas não
conta na votação da linha (só leituras novas do OCR confirmam a linha).

A câmera só fica aberta enquanto o serviço está lendo (espera ativa ou `--mirar-sempre`); sem
espera, ela é liberada em 10 s. Com `--janela`, aparece a imagem com os textos lidos (laranja) e o
letreiro seguido (verde), para conferir e gravar o vídeo da demonstração. Nada é gravado em disco.

## Rodar no Windows (notebook do ponto)

```powershell
cd edge
.\iniciar.ps1                  # webcam + janela (pede a senha do MQTT camera-demo)
.\iniciar.ps1 -Braco           # também mira sem espera aberta (demo do braço)
.\iniciar.ps1 -Modo teclado    # sem câmera
.\iniciar.ps1 -Braco -Camera "http://192.168.0.50:81/stream?t=TOKEN"   # vídeo da ESP32-CAM
```

Na primeira vez, o script cria o `.venv` e instala tudo (alguns minutos). A senha do MQTT é pedida
na hora e não fica gravada; pegue no CloudShell:
`aws ssm get-parameter --name /sonar/mqtt/usuarios/camera-demo --with-decryption --query Parameter.Value --output text`.

## Sem o Sonar Ponto: câmera do celular

Com `-SemPonto` (`--sem-ponto`), a câmera faz o papel do ultrassom: o letreiro na frente dela é o
ônibus no ponto. Letreiro parado por 3 s = **parou** (avisa na hora, com o ônibus ainda no ponto);
letreiro que some antes disso, atravessando o quadro = **passou direto** (o passageiro pode
reclamar). O aviso vai em `sonar/parada/{id}/camera/passagem`:

```json
{"linha_lida": "DEMO-20", "confianca": 0.93, "tempo_parado_s": 3.1, "parou": true, "passou_em": "2026-11-14T13:05:00Z"}
```

A API só usa esse aviso quando o Sonar Ponto da parada está offline (com ele ligado, quem decide é
ele) e, na demonstração, deixa de simular os ônibus enquanto a câmera estiver ligada nesse modo.

Celular como câmera (Android ou iPhone):

1. Instale o **DroidCam** no celular (no Android, o **IP Webcam** também serve, na porta 8080) e
   deixe celular e notebook na mesma rede Wi-Fi. Se a rede da faculdade isolar os aparelhos, ligue
   o notebook no roteador do celular.
2. Abra o app: ele mostra o IP. Confira no navegador do notebook: `http://IP:4747/video`.
3. No notebook: `.\iniciar.ps1 -SemPonto -Camera "http://IP:4747/video"`.
4. No app do passageiro (o navegador do notebook serve): "quero ir para o hospital" → "sim" →
   "cheguei". A câmera liga (ela só lê com alguém esperando).
5. Aponte o celular para os letreiros impressos (`python visao/imprimir.py`):
   - DEMO-10 parado na frente → "Chegando agora: linha DEMO-10. Não é o seu."
   - DEMO-20 parado por 3 s → "Chegando agora: linha DEMO-20. É o seu."
   - DEMO-20 passando pelo quadro sem parar → "passou sem parar. Quer registrar uma reclamação?"

Deixe "Mais opções" → cenário em **automático**: os outros cenários simulam os ônibus por conta própria.

## Rodar no Linux/macOS

```bash
cd edge
pip install -r requirements.txt            # modo teclado (sem câmera)
pip install -r requirements-visao.txt      # modo webcam
pip uninstall -y opencv-python-headless && pip install --force-reinstall --no-deps opencv-python  # janela

export SONAR_MQTT_HOST=sonar.rodrigoviana.app.br SONAR_MQTT_PORTA=8883
export SONAR_MQTT_USUARIO=camera-demo
export SONAR_MQTT_SENHA='...'   # do Parameter Store

python -m sonar_camera --parada demo --linhas DEMO-10,DEMO-20                    # digite a linha no terminal
python -m sonar_camera --parada demo --linhas DEMO-10 --mirar-sempre              # DEMO-10@0.2 = letreiro à esquerda
python -m sonar_camera --parada demo --linhas DEMO-10,DEMO-20 --modo webcam --janela
python -m sonar_camera --parada demo --linhas DEMO-10,DEMO-20 --modo webcam --janela --sem-ponto --camera http://IP:4747/video
```

Para testar contra o compose local (sem TLS): `SONAR_MQTT_HOST=localhost SONAR_MQTT_PORTA=1883 SONAR_MQTT_TLS=0`.

## Onde a equipe de Visão entra

Treina o modelo em [`visao/`](../visao/README.md) (com dataset sintético, sem rotular nada, e/ou
fotos reais) e o `treinar.py` copia o resultado para `edge/modelos/letreiro.pt`. Para trocar a
abordagem, basta outro localizador em `sonar_camera/detectores.py`: uma função que recebe o quadro e
devolve a lista de `Leitura(texto, confianca, x, y, caixa)`.

Testes: `pip install -r requirements-dev.txt && pytest`.
