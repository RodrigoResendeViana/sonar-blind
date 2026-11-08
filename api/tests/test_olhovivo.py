import asyncio

import httpx
import pytest

from sonar_api.olhovivo import ClienteOlhoVivo, OlhoVivoIndisponivel, interpretar_previsao

RESPOSTA = {
    "hr": "20:09",
    "p": {
        "cp": 4200953,
        "np": "PARADA EXEMPLO",
        "py": -23.67,
        "px": -46.75,
        "l": [
            {
                "c": "7021-10",
                "cl": 1989,
                "sl": 1,
                "lt0": "TERM. JOÃO DIAS",
                "lt1": "JD. MARACÁ",
                "qv": 2,
                "vs": [
                    {"p": "74558", "t": "20:14", "a": True, "ta": "2026-11-08T23:09:05Z", "py": -23.67, "px": -46.75},
                    {"p": "74560", "t": "20:11", "a": False, "ta": "2026-11-08T23:09:05Z", "py": -23.66, "px": -46.74},
                ],
            }
        ],
    },
}


def test_interpreta_e_ordena_por_chegada():
    veiculos = interpretar_previsao(RESPOSTA)
    assert [v.prefixo for v in veiculos] == ["74560", "74558"]
    assert veiculos[0].minutos == 2
    assert veiculos[0].destino == "TERM. JOÃO DIAS"
    assert veiculos[1].acessivel is True


def test_virada_da_meia_noite():
    dados = {"hr": "23:58", "p": {"l": [{"c": "N101-11", "lt0": "X", "vs": [{"p": "1", "t": "00:03"}]}]}}
    assert interpretar_previsao(dados)[0].minutos == 5


def test_resposta_vazia():
    assert interpretar_previsao({"hr": "10:00", "p": None}) == []


def _cliente(responder) -> tuple[ClienteOlhoVivo, list[str]]:
    chamadas: list[str] = []

    def transporte(requisicao: httpx.Request) -> httpx.Response:
        chamadas.append(requisicao.url.path)
        return responder(requisicao, len(chamadas))

    cliente = ClienteOlhoVivo("token-fake", "https://olhovivo.exemplo/v2.1", 30, transport=httpx.MockTransport(transporte))
    return cliente, chamadas


def test_autentica_uma_vez_e_usa_o_cache():
    def responder(requisicao, _n):
        if requisicao.url.path.endswith("/Login/Autenticar"):
            return httpx.Response(200, json=True, headers={"set-cookie": "apiCredentials=abc; Path=/"})
        assert "apiCredentials=abc" in requisicao.headers.get("cookie", "")
        return httpx.Response(200, json=RESPOSTA)

    cliente, chamadas = _cliente(responder)

    async def cenario():
        primeira = await cliente.previsao_parada(4200953)
        segunda = await cliente.previsao_parada(4200953)
        await cliente.fechar()
        return primeira, segunda

    primeira, segunda = asyncio.run(cenario())
    assert primeira == segunda
    assert chamadas == ["/v2.1/Login/Autenticar", "/v2.1/Previsao/Parada"]


def test_reautentica_quando_a_sessao_expira():
    def responder(requisicao, n):
        if requisicao.url.path.endswith("/Login/Autenticar"):
            return httpx.Response(200, json=True)
        return httpx.Response(401) if n == 2 else httpx.Response(200, json=RESPOSTA)

    cliente, chamadas = _cliente(responder)
    veiculos = asyncio.run(cliente.previsao_parada(1))
    assert len(veiculos) == 2
    assert chamadas.count("/v2.1/Login/Autenticar") == 2


def test_token_recusado_vira_indisponivel():
    cliente, _ = _cliente(lambda _req, _n: httpx.Response(200, json=False))
    with pytest.raises(OlhoVivoIndisponivel):
        asyncio.run(cliente.previsao_parada(1))


def test_erro_de_rede_vira_indisponivel():
    def responder(requisicao, _n):
        raise httpx.ConnectError("sem rede", request=requisicao)

    cliente, _ = _cliente(responder)
    with pytest.raises(OlhoVivoIndisponivel):
        asyncio.run(cliente.previsao_parada(1))


def test_sem_token_nao_consulta():
    cliente = ClienteOlhoVivo("", transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(OlhoVivoIndisponivel):
        asyncio.run(cliente.previsao_parada(1))
