"""Ponte entre a API e o broker MQTT (Mosquitto).

Tópicos (ver docs/contratos.md):
  API -> Sonar Ponto  sonar/parada/{id}/cmd            (retido)
  Ponto -> API        sonar/parada/{id}/evento, /status
  Câmera -> API       sonar/parada/{id}/camera/status
  API -> Sonar Bordo  sonar/onibus/{prefixo}/alerta
  Bordo -> API        sonar/onibus/{prefixo}/ciente, /status
"""

import json
import logging
import secrets
from collections.abc import Callable
from typing import Protocol

import paho.mqtt.client as mqtt

from .metricas import MQTT_CONECTADO

log = logging.getLogger("sonar.mqtt")

TOPICOS_ASSINADOS = [
    "sonar/parada/+/evento",
    "sonar/parada/+/status",
    "sonar/parada/+/camera/status",
    "sonar/parada/+/camera/passagem",  # câmera sem o Sonar Ponto (ex.: celular)
    "sonar/onibus/+/ciente",
    "sonar/onibus/+/status",
]


class Publicador(Protocol):
    def publicar(self, topico: str, dados: dict, retido: bool = False) -> None: ...


class PublicadorMemoria:
    """Usado nos testes e quando não há broker configurado (modo só simuladores)."""

    def __init__(self) -> None:
        self.mensagens: list[tuple[str, dict, bool]] = []

    def publicar(self, topico: str, dados: dict, retido: bool = False) -> None:
        self.mensagens.append((topico, dados, retido))


class PonteMqtt:
    def __init__(
        self,
        host: str,
        porta: int,
        usuario: str,
        senha: str,
        tls: bool,
        ao_receber: Callable[[str, dict], None],
    ):
        self._host, self._porta, self._ao_receber = host, porta, ao_receber
        self._cliente = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"sonar-api-{secrets.token_hex(4)}",
            protocol=mqtt.MQTTv311,
        )
        if usuario:
            self._cliente.username_pw_set(usuario, senha or None)
        if tls:
            self._cliente.tls_set()
        self._cliente.reconnect_delay_set(min_delay=1, max_delay=30)
        self._cliente.on_connect = self._conectou
        self._cliente.on_disconnect = self._desconectou
        self._cliente.on_message = self._mensagem
        self.conectado = False
        MQTT_CONECTADO.set(0)

    def iniciar(self) -> None:
        self._cliente.connect_async(self._host, self._porta, keepalive=30)
        self._cliente.loop_start()

    def parar(self) -> None:
        self._cliente.disconnect()
        self._cliente.loop_stop()

    def publicar(self, topico: str, dados: dict, retido: bool = False) -> None:
        self._cliente.publish(topico, json.dumps(dados, ensure_ascii=False), qos=1, retain=retido)

    def _conectou(self, cliente, _userdata, _flags, reason_code, _properties) -> None:
        if reason_code.is_failure:
            log.error("broker MQTT recusou a conexão: %s", reason_code)
            self.conectado = False
            MQTT_CONECTADO.set(0)
            return
        self.conectado = True
        MQTT_CONECTADO.set(1)
        cliente.subscribe([(topico, 1) for topico in TOPICOS_ASSINADOS])
        log.info("conectado ao broker MQTT %s:%s", self._host, self._porta)

    def _desconectou(self, _cliente, _userdata, _flags, reason_code, _properties) -> None:
        self.conectado = False
        MQTT_CONECTADO.set(0)
        log.warning("desconectado do broker MQTT: %s", reason_code)

    def _mensagem(self, _cliente, _userdata, mensagem) -> None:
        try:
            dados = json.loads(mensagem.payload.decode("utf-8")) if mensagem.payload else {}
        except (UnicodeDecodeError, ValueError):
            log.warning("mensagem MQTT ignorada (JSON inválido) em %s", mensagem.topic)
            return
        if not isinstance(dados, dict):
            return
        try:
            self._ao_receber(mensagem.topic, dados)
        except Exception:  # um dispositivo com defeito não derruba a ponte
            log.exception("falha ao processar mensagem de %s", mensagem.topic)
