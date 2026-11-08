# Serviço da câmera do Sonar Ponto

Roda no notebook do ponto. Lê a webcam **só enquanto há uma espera ativa**, acha o letreiro com
o YOLO da equipe de Visão, lê o texto com OCR, casa com o vocabulário restrito da parada, confirma
depois de 3 quadros seguidos iguais e publica só o texto em `sonar/parada/{id}/visao`:

```json
{"linha_lida": "DEMO-10", "confianca": 0.91, "passou_em": "2026-11-12T13:05:00Z"}
```

Nenhuma imagem sai do notebook. O Sonar Ponto (ESP32) junta essa leitura com o ultrassom e decide.

## Rodar

```bash
cd edge
pip install -r requirements.txt            # modo teclado (sem câmera)
pip install -r requirements-visao.txt      # modo webcam

export SONAR_MQTT_HOST=sonar.rodrigoviana.app.br SONAR_MQTT_PORTA=8883
export SONAR_MQTT_USUARIO=camera-demo
export SONAR_MQTT_SENHA="$(aws ssm get-parameter --name /sonar/mqtt/usuarios/camera-demo --with-decryption --query Parameter.Value --output text)"

python -m sonar_camera --parada demo --linhas DEMO-10,DEMO-20                 # digite a linha no terminal
python -m sonar_camera --parada demo --linhas DEMO-10,DEMO-20 --modo webcam --modelo modelos/letreiro.pt
```

Para testar contra o compose local (sem TLS): `SONAR_MQTT_HOST=localhost SONAR_MQTT_PORTA=1883 SONAR_MQTT_TLS=0`.

## Onde a equipe de Visão entra

`DetectorWebcam` em `sonar_camera/detectores.py` espera um modelo YOLO treinado para achar o
letreiro (`modelos/letreiro.pt`, fora do Git). Para trocar a abordagem, basta outra classe com o
método `ler()` que devolve a lista de `Leitura(texto, confianca)` do quadro atual.

Testes: `pip install -r requirements-dev.txt && pytest`.
