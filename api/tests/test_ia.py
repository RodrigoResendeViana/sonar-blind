import httpx
import pytest
from fastapi.testclient import TestClient

from sonar_api.ia import extrair_linhas
from sonar_api.main import create_app


def perguntar(cliente, texto, parada_id="demo"):
    resposta = cliente.post("/ia/perguntar", json={"texto": texto, "parada_id": parada_id})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def test_responde_com_previsao_e_fonte(cliente):
    corpo = perguntar(cliente, "quero pegar a linha DEMO-10")
    assert corpo["status"] == "ok"
    assert corpo["acao"] == {"tipo": "esperar", "parada_id": "demo", "linhas": ["DEMO-10"]}
    assert corpo["fontes"] == ["demonstracao:previsao"]
    assert "Dados de demonstração" in corpo["resposta_falada"]


def test_linha_que_nao_passa_no_ponto_e_nao_consta(cliente):
    corpo = perguntar(cliente, "a linha 8000-10 passa aqui?")
    assert corpo["status"] == "nao_consta"
    assert "Não consta a linha 8000-10" in corpo["resposta_falada"]


def test_sem_linha_sugere_as_do_ponto(cliente):
    corpo = perguntar(cliente, "quero ir pro trabalho")
    assert corpo["status"] == "nao_consta"
    assert "DEMO-10" in corpo["resposta_falada"]


def test_sem_parada_nao_inventa(cliente):
    corpo = perguntar(cliente, "linha DEMO-10", parada_id=None)
    assert corpo["status"] == "nao_consta"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("linha 8000 10", ["8000-10"]),
        ("quero o 971D-10", ["971D-10"]),
        ("vou para 10 de março", []),
        ("linha demo", []),
        ("linha DEMO 10", ["DEMO-10"]),
    ],
)
def test_extrair_linhas(texto, esperado):
    assert extrair_linhas(texto, ["DEMO-10", "DEMO-20"]) == esperado


def _app_com_ia(cfg, publicador, responder):
    cfg = cfg.model_copy(update={"ia_url": "http://ia.local"})
    return create_app(cfg, publicador=publicador, transporte_http=httpx.MockTransport(responder))


def test_repassa_para_o_agente_de_ia(cfg, publicador):
    resposta_ia = {"status": "ok", "resposta_falada": "Linha X em 3 minutos.", "acao": None, "fontes": ["gtfs:1"], "confianca": 0.8}
    app = _app_com_ia(cfg, publicador, lambda req: httpx.Response(200, json=resposta_ia))
    with TestClient(app) as cliente:
        assert perguntar(cliente, "oi") == resposta_ia


def test_resposta_fora_do_contrato_vira_nao_consta(cfg, publicador):
    app = _app_com_ia(cfg, publicador, lambda req: httpx.Response(200, json={"texto": "livre"}))
    with TestClient(app) as cliente:
        assert perguntar(cliente, "oi")["status"] == "nao_consta"


def test_ia_fora_do_ar_vira_tente_de_novo(cfg, publicador):
    def responder(requisicao):
        raise httpx.ConnectError("fora", request=requisicao)

    app = _app_com_ia(cfg, publicador, responder)
    with TestClient(app) as cliente:
        corpo = perguntar(cliente, "oi")
    assert corpo["status"] == "nao_consta"
    assert "Tente de novo" in corpo["resposta_falada"]


def test_limite_de_requisicoes(cfg, publicador):
    app = create_app(cfg.model_copy(update={"limite_por_minuto": 4}), publicador=publicador)
    with TestClient(app) as cliente:
        codigos = [
            cliente.post("/ia/perguntar", json={"texto": "linha DEMO-10", "parada_id": "demo"}).status_code
            for _ in range(4)
        ]
    assert codigos == [200, 200, 429, 429]
