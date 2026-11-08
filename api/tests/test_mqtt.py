from types import SimpleNamespace

from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.reasoncodes import ReasonCode

from sonar_api.mqtt_ponte import TOPICOS_ASSINADOS, PonteMqtt


def _ponte(ao_receber):
    return PonteMqtt("localhost", 1883, "sonar-api", "senha-fake", False, ao_receber)


def _mensagem(payload: bytes):
    return SimpleNamespace(topic="sonar/parada/demo/evento", payload=payload)


def test_entrega_json_valido_e_ignora_o_resto():
    recebidos = []
    ponte = _ponte(lambda topico, dados: recebidos.append((topico, dados)))
    ponte._mensagem(None, None, _mensagem(b'{"linha_lida": "DEMO-10"}'))
    ponte._mensagem(None, None, _mensagem(b"isto nao e json"))
    ponte._mensagem(None, None, _mensagem(b"[1, 2, 3]"))
    ponte._mensagem(None, None, _mensagem(b"\xff\xfe"))
    assert recebidos == [("sonar/parada/demo/evento", {"linha_lida": "DEMO-10"})]


def test_falha_ao_processar_nao_derruba_a_ponte():
    def explode(_topico, _dados):
        raise RuntimeError("dispositivo com defeito")

    _ponte(explode)._mensagem(None, None, _mensagem(b"{}"))


def test_assina_os_topicos_quando_conecta():
    assinados = []
    cliente = SimpleNamespace(subscribe=lambda topicos: assinados.extend(topicos))
    ponte = _ponte(lambda *_: None)

    ponte._conectou(cliente, None, None, ReasonCode(PacketTypes.CONNACK, "Success"), None)
    assert ponte.conectado is True
    assert [topico for topico, _qos in assinados] == TOPICOS_ASSINADOS

    ponte._conectou(cliente, None, None, ReasonCode(PacketTypes.CONNACK, "Not authorized"), None)
    assert ponte.conectado is False
