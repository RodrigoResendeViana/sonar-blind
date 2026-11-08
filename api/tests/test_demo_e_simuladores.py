import time

from conftest import criar_espera, ler_sse, mensagens
from sonar_api.olhovivo import Veiculo


def _esperar(cliente, espera_id, condicao, limite_s=10):
    fim = time.time() + limite_s
    while time.time() < fim:
        estado = cliente.get(f"/esperas/{espera_id}").json()
        if condicao(estado):
            return estado
        time.sleep(0.05)
    raise AssertionError(f"condição não atingida: {estado}")


def test_demo_roda_a_jornada_inteira(cliente, publicador):
    resposta = cliente.post("/demo/esperas", json={"cenario": "embarque"})
    assert resposta.status_code == 201
    espera_id = resposta.json()["id"]
    estado = _esperar(cliente, espera_id, lambda e: e["passagem"] and e["passagem"]["linha"] == "DEMO-10")
    assert estado["aviso"]["prefixo"] == "90001"
    assert estado["aviso"]["ciente_em"]
    assert mensagens(publicador, "sonar/onibus/90001/alerta")
    corpo = cliente.post(f"/esperas/{espera_id}/embarque", json={"origem": "toque"}).json()
    assert corpo["embarque"]["validado_por_camera"] is True
    tipos = [e["tipo"] for e in ler_sse(cliente, f"/esperas/{espera_id}/eventos")]
    assert tipos.count("onibus_chegando") == 2


def test_demo_do_onibus_que_nao_para(cliente):
    espera_id = cliente.post("/demo/esperas", json={"cenario": "nao_parou"}).json()["id"]
    estado = _esperar(cliente, espera_id, lambda e: e["ocorrencia"] is not None)
    assert estado["ocorrencia"]["status"] == "aguardando_consentimento"


def test_motorista_simulado_recebe_e_confirma(cliente, sonar):
    espera_id = criar_espera(cliente)["id"]
    sonar.processar_previsao("demo", [Veiculo("DEMO-10", "Terminal Exemplo", "90001", 3)], None)
    alertas = ler_sse(cliente, "/simulador/motorista/eventos?uma_vez=true")
    assert alertas[0]["prefixo"] == "90001"
    assert alertas[0]["espera_id"] == espera_id
    resposta = cliente.post("/simulador/onibus/90001/ciente", json={"espera_id": espera_id})
    assert resposta.json() == {"registrado": True}
    assert ler_sse(cliente, "/simulador/motorista/eventos?uma_vez=true") == []


def test_ponto_simulado(cliente):
    criar_espera(cliente, linhas=("DEMO-10", "DEMO-20"))
    estado = ler_sse(cliente, "/simulador/paradas/demo/eventos?uma_vez=true")[0]
    assert estado["esperas_ativas"] == 1
    assert estado["linhas_alvo"] == ["DEMO-10", "DEMO-20"]
    resposta = cliente.post("/simulador/paradas/demo/deteccao", json={"linha_lida": "DEMO-20", "tempo_parado_s": 7})
    assert resposta.json() == {"esperas_afetadas": 1}


def test_simuladores_podem_ser_desligados(cfg, publicador):
    from fastapi.testclient import TestClient

    from sonar_api.main import create_app

    app = create_app(cfg.model_copy(update={"simuladores": False}), publicador=publicador)
    with TestClient(app) as cliente:
        assert cliente.post("/demo/esperas", json={}).status_code == 404
