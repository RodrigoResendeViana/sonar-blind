import json

import httpx

from sonar_rpa.robo import processar


def montar(pendentes):
    atualizacoes = {}

    def tratar(req: httpx.Request):
        if req.method == "GET":
            return httpx.Response(200, json=pendentes)
        atualizacoes[req.url.path] = json.loads(req.content)
        return httpx.Response(200, json={})

    cliente = httpx.Client(base_url="http://api", transport=httpx.MockTransport(tratar))
    return cliente, atualizacoes


def test_registra_e_devolve_protocolo():
    cliente, atualizacoes = montar([{"id": 1, "linha": "8000-10"}])
    assert processar(cliente)["enviada"] == 1
    assert atualizacoes["/ocorrencias/1"]["status"] == "enviada"
    assert atualizacoes["/ocorrencias/1"]["protocolo"].startswith("SIM-")


def test_dados_incompletos_viram_inconclusiva():
    cliente, atualizacoes = montar([{"id": 2, "linha": None}])
    processar(cliente)
    assert atualizacoes["/ocorrencias/2"] == {"status": "inconclusiva", "protocolo": None}


def test_falha_no_portal_vira_erro():
    cliente, atualizacoes = montar([{"id": 3, "linha": "8000-10"}])
    processar(cliente, simular=False)
    assert atualizacoes["/ocorrencias/3"]["status"] == "erro"
