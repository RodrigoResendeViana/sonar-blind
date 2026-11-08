import json

import pytest
from fastapi.testclient import TestClient

from sonar_api.config import Settings
from sonar_api.main import create_app
from sonar_api.mqtt_ponte import PublicadorMemoria

TOKEN_TESTE = "teste"


@pytest.fixture
def cfg() -> Settings:
    return Settings(
        database_url="sqlite+pysqlite:///:memory:",
        sal_hash="sal",
        token_servico=TOKEN_TESTE,
        olhovivo_token="",
        mqtt_host="",
        monitor_intervalo_s=3600,
        demo_velocidade=100,
        limite_por_minuto=1000,
    )


@pytest.fixture
def publicador() -> PublicadorMemoria:
    return PublicadorMemoria()


@pytest.fixture
def app(cfg, publicador):
    return create_app(cfg, publicador=publicador)


@pytest.fixture
def cliente(app):
    with TestClient(app) as cliente:
        yield cliente


@pytest.fixture
def sonar(app):
    return app.state.sonar


def criar_espera(cliente, linhas=("DEMO-10",), **extra) -> dict:
    resposta = cliente.post(
        "/esperas",
        json={"parada_id": "demo", "linhas": list(linhas), **extra},
        headers={"X-Sonar-Usuario": "usuario-1"},
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def mensagens(publicador: PublicadorMemoria, topico: str) -> list[dict]:
    return [dados for t, dados, _retido in publicador.mensagens if t == topico]


def ler_sse(cliente, caminho: str, headers: dict | None = None) -> list[dict]:
    with cliente.stream("GET", caminho, headers=headers or {}) as resposta:
        assert resposta.status_code == 200
        assert resposta.headers["content-type"].startswith("text/event-stream")
        corpo = "".join(resposta.iter_text())
    return [json.loads(linha[6:]) for linha in corpo.splitlines() if linha.startswith("data: ")]
