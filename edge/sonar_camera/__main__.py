"""python -m sonar_camera --parada demo --linhas DEMO-10,DEMO-20 [--modo webcam] [--janela] [--sem-ponto]

Variáveis: SONAR_MQTT_HOST, SONAR_MQTT_PORTA (8883), SONAR_MQTT_USUARIO (camera-<parada>),
SONAR_MQTT_SENHA e SONAR_MQTT_TLS (1). A senha está no Parameter Store:
/sonar/mqtt/usuarios/camera-<parada>.
"""

import argparse
import json
import logging
import os

import paho.mqtt.client as mqtt

from .detectores import DetectorCamera, DetectorTeclado, escolher_localizador
from .servico import ServicoCamera

log = logging.getLogger("sonar.camera")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    argumentos = argparse.ArgumentParser(description="Serviço da câmera do Sonar Ponto")
    argumentos.add_argument("--parada", default="demo")
    argumentos.add_argument("--linhas", default="", help="linhas que passam no ponto, separadas por vírgula")
    argumentos.add_argument("--modo", choices=["teclado", "webcam"], default="teclado")
    argumentos.add_argument(
        "--camera",
        default="0",
        help="número da webcam (0, 1...) ou URL do vídeo: celular com DroidCam (http://<ip>:4747/video) "
        "ou ESP32-CAM (http://<ip>:81/stream?t=<token>)",
    )
    argumentos.add_argument("--modelo", default="modelos/letreiro.pt")
    argumentos.add_argument(
        "--detector",
        choices=["auto", "yolo", "ocr"],
        default="auto",
        help="auto: YOLO se o modelo existir, senão só OCR (funciona sem treinar nada)",
    )
    argumentos.add_argument("--janela", action="store_true", help="mostra a câmera com o letreiro marcado (para o vídeo)")
    argumentos.add_argument(
        "--mirar-sempre", action="store_true", help="publica a posição do letreiro mesmo sem espera (demo do braço)"
    )
    argumentos.add_argument(
        "--sem-ponto",
        action="store_true",
        help="sem o Sonar Ponto: a câmera avisa sozinha a chegada do ônibus (letreiro parado 3 s = parou)",
    )
    opcoes = argumentos.parse_args()

    if opcoes.modo == "webcam":
        camera = int(opcoes.camera) if opcoes.camera.isdigit() else opcoes.camera
        detector = DetectorCamera(escolher_localizador(opcoes.detector, opcoes.modelo), camera, opcoes.janela)
    else:
        detector = DetectorTeclado()
    cliente = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"camera-{opcoes.parada}",
        protocol=mqtt.MQTTv311,
    )

    def publicar(topico: str, dados: dict, retido: bool) -> None:
        cliente.publish(topico, json.dumps(dados), qos=1, retain=retido)

    linhas = [linha.strip() for linha in opcoes.linhas.split(",") if linha.strip()]
    servico = ServicoCamera(
        opcoes.parada, detector, publicar, linhas, mirar_sempre=opcoes.mirar_sempre, sem_ponto=opcoes.sem_ponto
    )

    cliente.username_pw_set(os.environ.get("SONAR_MQTT_USUARIO", f"camera-{opcoes.parada}"), os.environ.get("SONAR_MQTT_SENHA"))
    if os.environ.get("SONAR_MQTT_TLS", "1") == "1":
        cliente.tls_set()
    cliente.will_set(servico.topico_status, json.dumps({"online": False}), qos=1, retain=True)

    def conectou(cli, _dados, _flags, codigo, _props):
        if codigo.is_failure:
            log.error("broker recusou: %s", codigo)
            return
        cli.subscribe(servico.topico_cmd, qos=1)
        servico.status()
        log.info("conectado; aguardando espera ativa na parada %s", opcoes.parada)
        if opcoes.sem_ponto:
            log.info("sem o Sonar Ponto: a câmera avisa sozinha quando o ônibus para ou passa direto")

    def mensagem(_cli, _dados, msg):
        try:
            servico.ao_comando(json.loads(msg.payload or b"{}"))
            log.info("comando: ativo=%s linhas=%s", servico.ativo, servico.linhas_alvo)
        except ValueError:
            log.warning("comando ignorado: JSON inválido")

    cliente.on_connect = conectou
    cliente.on_message = mensagem
    cliente.connect_async(os.environ.get("SONAR_MQTT_HOST", "localhost"), int(os.environ.get("SONAR_MQTT_PORTA", "8883")))
    cliente.loop_start()
    if opcoes.modo == "teclado":
        print("Digite a linha que a câmera estaria lendo (ex.: DEMO-10, ou DEMO-10@0.2 para a esquerda).")
    try:
        servico.rodar()
    except KeyboardInterrupt:
        pass
    finally:
        if hasattr(detector, "fechar"):
            detector.fechar()
        servico.status(online=False)
        cliente.loop_stop()
        cliente.disconnect()


if __name__ == "__main__":
    main()
