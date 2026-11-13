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


def test_resposta_fora_do_contrato_cai_para_as_regras(cfg, publicador):
    app = _app_com_ia(cfg, publicador, lambda req: httpx.Response(200, json={"texto": "livre"}))
    with TestClient(app) as cliente:
        corpo = perguntar(cliente, "oi")
    assert corpo["status"] == "nao_consta"
    assert "Não entendi qual linha" in corpo["resposta_falada"]  # resposta das regras, não do agente


def test_ia_fora_do_ar_responde_pelas_regras(cfg, publicador):
    def responder(requisicao):
        raise httpx.ConnectError("fora", request=requisicao)

    app = _app_com_ia(cfg, publicador, responder)
    with TestClient(app) as cliente:
        corpo = cliente.post("/ia/perguntar", json={"texto": "quando chega a linha DEMO-10?", "parada_id": "demo"}).json()
    assert corpo["status"] == "ok"
    assert "DEMO-10" in corpo["resposta_falada"]
    assert corpo["acao"]["linhas"] == ["DEMO-10"]


def test_agente_lento_responde_pelas_regras(cfg, publicador):
    lento = {"status": "nao_consta", "resposta_falada": "Não consegui responder agora. Tente de novo em instantes."}
    app = _app_com_ia(cfg, publicador, lambda req: httpx.Response(200, json=lento))
    with TestClient(app) as cliente:
        corpo = cliente.post("/ia/perguntar", json={"texto": "linha DEMO-20", "parada_id": "demo"}).json()
    assert corpo["status"] == "ok"
    assert "DEMO-20" in corpo["resposta_falada"]


def test_nao_consta_do_agente_vale_quando_as_regras_tambem_nao_sabem(cfg, publicador):
    resposta_ia = {"status": "nao_consta", "resposta_falada": "Eu só ajudo com os ônibus do ponto."}
    app = _app_com_ia(cfg, publicador, lambda req: httpx.Response(200, json=resposta_ia))
    with TestClient(app) as cliente:
        corpo = cliente.post("/ia/perguntar", json={"texto": "me conta uma piada", "parada_id": "demo"}).json()
    assert corpo["resposta_falada"] == "Eu só ajudo com os ônibus do ponto."


def test_limite_de_requisicoes(cfg, publicador):
    app = create_app(cfg.model_copy(update={"limite_por_minuto": 4}), publicador=publicador)
    with TestClient(app) as cliente:
        codigos = [
            cliente.post("/ia/perguntar", json={"texto": "linha DEMO-10", "parada_id": "demo"}).status_code
            for _ in range(4)
        ]
    assert codigos == [200, 200, 429, 429]
