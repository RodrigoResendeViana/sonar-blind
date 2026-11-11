import json

import httpx
from fastapi.testclient import TestClient

from sonar_ia.main import criar_app

PREVISAO = {
    "parada": {"id": "demo", "nome": "Ponto de demonstração"},
    "fonte": "demonstracao",
    "veiculos": [{"linha": "DEMO-10", "destino": "Terminal Exemplo", "minutos": 4}],
}
LINHAS = {"fonte": "olhovivo", "linhas": [{"codigo": "8000-10", "origem": "PCA RAMOS", "destino": "TERMINAL LAPA"}]}


def api_falsa():
    def tratar(req: httpx.Request):
        if req.url.path == "/linhas":
            return httpx.Response(200, json=LINHAS)
        if req.url.path == "/paradas/demo/previsao":
            return httpx.Response(200, json=PREVISAO)
        return httpx.Response(404)

    return httpx.AsyncClient(base_url="http://api", transport=httpx.MockTransport(tratar))


def ollama_roteirizado(roteiro: list[dict], vistos: list | None = None):
    """Devolve, em ordem, as mensagens do roteiro (como se fosse o LLM)."""
    fila = list(roteiro)

    def tratar(req: httpx.Request):
        if vistos is not None:
            vistos.append(json.loads(req.content))
        return httpx.Response(200, json={"message": fila.pop(0)})

    return httpx.AsyncClient(base_url="http://ollama", transport=httpx.MockTransport(tratar))


def chamar(nome, **args):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": nome, "arguments": args}}]}


def cliente(roteiro, vistos=None):
    return TestClient(criar_app(ollama=ollama_roteirizado(roteiro, vistos), api=api_falsa()))


def test_previsao_com_ferramenta_vira_resposta_ok_e_acao():
    vistos = []
    roteiro = [
        chamar("previsao_parada", parada_id="demo"),
        {"role": "assistant", "content": "A linha **DEMO-10** chega em 4 minutos."},
    ]
    with cliente(roteiro, vistos) as c:
        corpo = c.post("/perguntar", json={"texto": "quando chega a DEMO-10?", "parada_id": "demo"}).json()
    assert corpo["status"] == "ok"
    assert corpo["resposta_falada"] == "A linha DEMO-10 chega em 4 minutos."
    assert corpo["acao"] == {"tipo": "esperar", "parada_id": "demo", "linhas": ["DEMO-10"]}
    assert corpo["fontes"] == ["demonstracao:previsao"]
    assert vistos[1]["messages"][-1]["role"] == "tool"


def test_busca_por_destino():
    roteiro = [
        chamar("buscar_linha", termo="Lapa"),
        {"role": "assistant", "content": "A linha 8000-10 vai para o Terminal Lapa."},
    ]
    with cliente(roteiro) as c:
        corpo = c.post("/perguntar", json={"texto": "quero ir para a Lapa"}).json()
    assert corpo["status"] == "ok"
    assert corpo["fontes"] == ["olhovivo:linhas"]
    assert corpo["acao"] is None  # sem parada, não há o que esperar


def test_sem_ferramenta_nao_repassa_o_que_o_modelo_inventou():
    roteiro = [{"role": "assistant", "content": "A linha 1234-56 chega em 2 minutos."}]
    with cliente(roteiro) as c:
        corpo = c.post("/perguntar", json={"texto": "e a 1234?"}).json()
    assert corpo["status"] == "nao_consta"
    assert "1234" not in corpo["resposta_falada"]


def test_ollama_fora_do_ar():
    def falhar(_req):
        raise httpx.ConnectError("sem ollama")

    ollama = httpx.AsyncClient(base_url="http://ollama", transport=httpx.MockTransport(falhar))
    with TestClient(criar_app(ollama=ollama, api=api_falsa())) as c:
        corpo = c.post("/perguntar", json={"texto": "oi"}).json()
    assert corpo["status"] == "nao_consta"


def test_ferramenta_rejeita_argumento_malicioso():
    roteiro = [
        chamar("previsao_parada", parada_id="../../ocorrencias"),
        {"role": "assistant", "content": "Não consta."},
    ]
    with cliente(roteiro) as c:
        corpo = c.post("/perguntar", json={"texto": "x", "parada_id": "demo"}).json()
    assert corpo["status"] == "nao_consta"


def test_rejeita_pergunta_vazia():
    with cliente([]) as c:
        assert c.post("/perguntar", json={"texto": ""}).status_code == 422
