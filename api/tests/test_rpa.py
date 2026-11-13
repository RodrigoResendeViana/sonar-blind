import httpx
from conftest import criar_espera
from fastapi.testclient import TestClient
from sonar_api import rpa
from sonar_api.main import create_app
from sonar_api.olhovivo import Veiculo


def _app_com_webhook(cfg, publicador):
    cfg.rpa_webhook_url = "http://n8n:5678/webhook/sonar-ocorrencia"
    return create_app(cfg, publicador=publicador)


def _passou_direto(cliente, sonar) -> str:
    espera_id = criar_espera(cliente)["id"]
    sonar.processar_previsao("demo", [Veiculo("DEMO-10", "Terminal Exemplo", "90001", 3)], None)
    sonar.processar_deteccao("demo", {"linha_lida": "DEMO-10", "confianca": 0.9, "tempo_parado_s": 0.5})
    return espera_id


def test_consentimento_avisa_o_robo_na_hora(cfg, publicador, monkeypatch):
    chamadas = []

    def post_falso(url, json, timeout):
        chamadas.append((url, json))
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(rpa.httpx, "post", post_falso)
    with TestClient(_app_com_webhook(cfg, publicador)) as cliente:
        sonar = cliente.app.state.sonar
        espera_id = _passou_direto(cliente, sonar)
        corpo = cliente.post(f"/esperas/{espera_id}/nao-parou", json={"consentimento": True}).json()
    assert chamadas == [("http://n8n:5678/webhook/sonar-ocorrencia", {"ocorrencia_id": corpo["ocorrencia"]["id"]})]


def test_sem_consentimento_nao_avisa(cfg, publicador, monkeypatch):
    chamadas = []
    monkeypatch.setattr(rpa.httpx, "post", lambda *a, **k: chamadas.append(a))
    with TestClient(_app_com_webhook(cfg, publicador)) as cliente:
        espera_id = _passou_direto(cliente, cliente.app.state.sonar)
        cliente.post(f"/esperas/{espera_id}/nao-parou", json={"consentimento": False})
    assert chamadas == []


def test_robo_fora_do_ar_nao_quebra_o_app(cfg, publicador, monkeypatch):
    def post_falha(url, json, timeout):
        raise httpx.ConnectError("n8n fora do ar")

    monkeypatch.setattr(rpa.httpx, "post", post_falha)
    with TestClient(_app_com_webhook(cfg, publicador)) as cliente:
        espera_id = _passou_direto(cliente, cliente.app.state.sonar)
        resposta = cliente.post(f"/esperas/{espera_id}/nao-parou", json={"consentimento": True})
    assert resposta.status_code == 200
    assert resposta.json()["ocorrencia"]["status"] == "pendente"
