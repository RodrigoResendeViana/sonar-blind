from fastapi.testclient import TestClient

from sonar_ia.main import app

cliente = TestClient(app)


def test_resposta_segue_o_contrato():
    r = cliente.post("/perguntar", json={"texto": "quero pegar a linha 8000-10", "parada_id": "itaquera-01"})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["status"] in {"ok", "nao_consta"}
    assert len(corpo["resposta_falada"]) <= 600
    assert 0.0 <= corpo["confianca"] <= 1.0


def test_sem_fonte_nao_inventa():
    corpo = cliente.post("/perguntar", json={"texto": "qual a previsão do tempo?"}).json()
    if corpo["status"] == "ok":
        assert corpo["fontes"], "resposta ok precisa citar fontes"


def test_rejeita_pergunta_vazia():
    assert cliente.post("/perguntar", json={"texto": ""}).status_code == 422
