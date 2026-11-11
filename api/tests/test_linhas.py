import asyncio

import httpx

from sonar_api.olhovivo import ClienteOlhoVivo, interpretar_linhas

BUSCA = [
    {"cl": 1273, "lc": False, "lt": "8000", "sl": 1, "tl": 10, "tp": "PCA.RAMOS DE AZEVEDO", "ts": "TERMINAL LAPA"},
    {"cl": 34041, "lc": False, "lt": "8000", "sl": 2, "tl": 10, "tp": "PCA.RAMOS DE AZEVEDO", "ts": "TERMINAL LAPA"},
]


def test_interpreta_os_dois_sentidos():
    ida, volta = interpretar_linhas(BUSCA)
    assert ida["codigo"] == "8000-10"
    assert (ida["origem"], ida["destino"]) == ("PCA.RAMOS DE AZEVEDO", "TERMINAL LAPA")
    assert (volta["origem"], volta["destino"]) == ("TERMINAL LAPA", "PCA.RAMOS DE AZEVEDO")


def test_cliente_busca_no_olho_vivo():
    def tratar(req: httpx.Request):
        if req.url.path.endswith("/Login/Autenticar"):
            return httpx.Response(200, json=True)
        assert req.url.params["termosBusca"] == "lapa"
        return httpx.Response(200, json=BUSCA)

    cliente = ClienteOlhoVivo("token", transport=httpx.MockTransport(tratar))
    linhas = asyncio.run(cliente.buscar_linhas("lapa"))
    assert {linha["destino"] for linha in linhas} == {"TERMINAL LAPA", "PCA.RAMOS DE AZEVEDO"}


def test_sem_token_busca_nas_linhas_cadastradas(cliente):
    corpo = cliente.get("/linhas", params={"termo": "demo-10"}).json()
    assert corpo["fonte"] == "demonstracao"
    assert [linha["codigo"] for linha in corpo["linhas"]] == ["DEMO-10"]


def test_busca_por_destino(cliente):
    corpo = cliente.get("/linhas", params={"termo": "terminal"}).json()
    assert corpo["linhas"][0]["parada_id"] == "demo"


def test_rejeita_termo_estranho(cliente):
    assert cliente.get("/linhas", params={"termo": "a"}).status_code == 422
    assert cliente.get("/linhas", params={"termo": "x; drop"}).status_code == 422
