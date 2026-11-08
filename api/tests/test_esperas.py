import hashlib
from datetime import timedelta

from conftest import TOKEN_TESTE, criar_espera, ler_sse, mensagens
from sonar_api.db import Espera, agora
from sonar_api.olhovivo import Veiculo

AUTORIZACAO = {"Authorization": f"Bearer {TOKEN_TESTE}"}


def test_criar_espera_liga_o_sonar_ponto(cliente, publicador):
    espera = criar_espera(cliente, lat=-23.5424, lon=-46.4712)
    assert espera["status"] == "aguardando"
    topico, comando, retido = publicador.mensagens[-1]
    assert topico == "sonar/parada/demo/cmd"
    assert retido is True
    assert comando["acao"] == "ativar"
    assert comando["linhas_alvo"] == ["DEMO-10"]
    cliente.post(f"/esperas/{espera['id']}/cancelar")
    primeiro = ler_sse(cliente, f"/esperas/{espera['id']}/eventos")[1]
    assert primeiro["tipo"] == "ponto_ativado"
    assert primeiro["fala"].startswith("Você está no ponto certo")


def test_rejeita_linha_e_parada_invalidas(cliente):
    assert cliente.post("/esperas", json={"parada_id": "demo", "linhas": ["xx"]}).status_code == 422
    assert cliente.post("/esperas", json={"parada_id": "nao-existe", "linhas": ["DEMO-10"]}).status_code == 404
    assert cliente.post("/esperas", json={"parada_id": "demo", "linhas": []}).status_code == 422


def test_jornada_completa_com_embarque_validado(cliente, sonar, publicador):
    espera_id = criar_espera(cliente)["id"]

    sonar.processar_previsao("demo", [Veiculo("DEMO-10", "Terminal Exemplo", "90001", 6)], None)
    assert not mensagens(publicador, "sonar/onibus/90001/alerta")

    sonar.processar_previsao("demo", [Veiculo("DEMO-10", "Terminal Exemplo", "90001", 4)], None)
    alerta = mensagens(publicador, "sonar/onibus/90001/alerta")[0]
    assert alerta == {
        "espera_id": espera_id,
        "parada_nome": "Ponto de demonstração (Itaquera)",
        "paradas_ate": 2,
        "linha": "DEMO-10",
    }

    sonar.receber_mqtt("sonar/onibus/90001/ciente", {"espera_id": espera_id})
    assert cliente.get(f"/esperas/{espera_id}").json()["aviso"]["ciente_em"]

    sonar.receber_mqtt("sonar/parada/demo/evento", {"linha_lida": "DEMO-20", "confianca": 0.9, "tempo_parado_s": 8})
    sonar.receber_mqtt("sonar/parada/demo/evento", {"linha_lida": "DEMO-10", "confianca": 0.95, "tempo_parado_s": 12})

    resposta = cliente.post(f"/esperas/{espera_id}/embarque", json={"origem": "voz"})
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "embarcou"
    assert resposta.json()["embarque"]["validado_por_camera"] is True
    assert mensagens(publicador, "sonar/parada/demo/cmd")[-1] == {"acao": "desativar"}

    eventos = ler_sse(cliente, f"/esperas/{espera_id}/eventos")
    tipos = [e["tipo"] for e in eventos]
    assert tipos == [
        "estado",
        "ponto_ativado",
        "previsao",
        "aviso_enviado",
        "motorista_ciente",
        "onibus_chegando",
        "onibus_chegando",
        "embarque_confirmado",
    ]
    assert "Não é o seu" in eventos[5]["fala"]
    assert "É o seu" in eventos[6]["fala"]
    assert eventos[6]["dados"]["vibrar"] == "longa"

    # reconexão: só o que veio depois do Last-Event-ID
    eventos = ler_sse(cliente, f"/esperas/{espera_id}/eventos", {"Last-Event-ID": str(eventos[4]["id"])})
    assert [e["tipo"] for e in eventos] == ["estado", "onibus_chegando", "onibus_chegando", "embarque_confirmado"]


def test_ciente_de_outro_onibus_e_ignorado(cliente, sonar):
    espera_id = criar_espera(cliente)["id"]
    sonar.processar_previsao("demo", [Veiculo("DEMO-10", "", "90001", 3)], None)
    assert sonar.registrar_ciente("99999", {"espera_id": espera_id}) is False
    assert sonar.registrar_ciente("90001", {}) is True


def test_sem_camera_avisa_sem_confirmacao_visual(cliente, sonar):
    espera_id = criar_espera(cliente)["id"]
    sonar.processar_deteccao("demo", {"linha_lida": None, "tempo_parado_s": 9})
    ultimo = cliente.get(f"/esperas/{espera_id}").json()
    assert ultimo["passagem"] is None
    sonar.cancelar_espera(espera_id)
    eventos = ler_sse(cliente, f"/esperas/{espera_id}/eventos")
    assert "sem confirmação visual" in eventos[2]["fala"]


def test_leitura_incerta_pede_confirmacao(cliente, sonar):
    espera_id = criar_espera(cliente)["id"]
    sonar.processar_deteccao("demo", {"linha_lida": "DEMO-10", "confianca": 0.4, "tempo_parado_s": 9})
    sonar.cancelar_espera(espera_id)
    eventos = ler_sse(cliente, f"/esperas/{espera_id}/eventos")
    assert "confirme com o motorista" in eventos[2]["fala"]


def test_onibus_que_passou_direto_vira_ocorrencia_com_protocolo(cliente, sonar):
    espera_id = criar_espera(cliente)["id"]
    sonar.processar_previsao("demo", [Veiculo("DEMO-10", "Terminal Exemplo", "90001", 3)], None)
    sonar.processar_deteccao("demo", {"linha_lida": "DEMO-10", "confianca": 0.9, "tempo_parado_s": 0.5})
    assert cliente.get(f"/esperas/{espera_id}").json()["ocorrencia"]["status"] == "aguardando_consentimento"

    resposta = cliente.post(f"/esperas/{espera_id}/nao-parou", json={"consentimento": True})
    assert resposta.json()["status"] == "nao_parou"
    assert resposta.json()["ocorrencia"]["status"] == "pendente"

    pendentes = cliente.get("/ocorrencias", params={"status": "pendente"}, headers=AUTORIZACAO).json()
    assert len(pendentes) == 1
    assert pendentes[0]["prefixo"] == "90001"
    assert pendentes[0]["evidencias"]["passagem"]["parou"] is False
    assert pendentes[0]["evidencias"]["aviso"]["prefixo"] == "90001"

    resposta = cliente.patch(
        f"/ocorrencias/{pendentes[0]['id']}", json={"status": "enviada", "protocolo": "2026-000123"}, headers=AUTORIZACAO
    )
    assert resposta.status_code == 200
    assert cliente.get(f"/esperas/{espera_id}").json()["ocorrencia"]["protocolo"] == "2026-000123"

    eventos = ler_sse(cliente, f"/esperas/{espera_id}/eventos")
    assert eventos[-1]["tipo"] == "ocorrencia_protocolo"
    assert "2026-000123" in eventos[-1]["fala"]


def test_embarque_depois_de_passar_direto_descarta_a_ocorrencia(cliente, sonar):
    espera_id = criar_espera(cliente)["id"]
    sonar.processar_deteccao("demo", {"linha_lida": "DEMO-10", "tempo_parado_s": 0.4})
    corpo = cliente.post(f"/esperas/{espera_id}/embarque", json={}).json()
    assert corpo["ocorrencia"]["status"] == "descartada"


def test_espera_encerrada_nao_aceita_nova_acao(cliente):
    espera_id = criar_espera(cliente)["id"]
    cliente.post(f"/esperas/{espera_id}/cancelar")
    assert cliente.post(f"/esperas/{espera_id}/embarque", json={}).status_code == 409
    assert cliente.post(f"/esperas/{espera_id}/nao-parou", json={"consentimento": False}).status_code == 409


def test_rotas_do_robo_exigem_token(cliente):
    assert cliente.get("/ocorrencias").status_code == 401
    assert cliente.get("/ocorrencias", headers={"Authorization": "Bearer errado"}).status_code == 401
    assert cliente.get("/ocorrencias", headers=AUTORIZACAO).status_code == 200


def test_usuario_e_guardado_so_como_hash(cliente, sonar):
    espera_id = criar_espera(cliente)["id"]
    with sonar._leitura() as sessao:
        espera = sessao.get(Espera, espera_id)
        assert espera.usuario_hash == hashlib.sha256(b"sal:usuario-1").hexdigest()


def test_pergunta_se_embarcou_e_depois_se_parou(cliente, sonar):
    espera_id = criar_espera(cliente)["id"]
    sonar.processar_deteccao("demo", {"linha_lida": "DEMO-10", "confianca": 0.9, "tempo_parado_s": 10})

    with sonar._transacao() as (sessao, _saida):
        sessao.get(Espera, espera_id).passagem_em = agora() - timedelta(seconds=50)
    sonar.verificar_temporizadores()
    with sonar._transacao() as (sessao, _saida):
        sessao.get(Espera, espera_id).passagem_em = agora() - timedelta(seconds=200)
    sonar.verificar_temporizadores()

    sonar.cancelar_espera(espera_id)
    tipos = [e["tipo"] for e in ler_sse(cliente, f"/esperas/{espera_id}/eventos")]
    assert tipos.index("perguntar_embarque") < tipos.index("perguntar_parou")


def test_espera_expira_e_desliga_o_ponto(cliente, sonar, publicador):
    espera_id = criar_espera(cliente)["id"]
    with sonar._transacao() as (sessao, _saida):
        sessao.get(Espera, espera_id).expira_em = agora() - timedelta(seconds=1)
    sonar.verificar_temporizadores()
    assert cliente.get(f"/esperas/{espera_id}").json()["status"] == "expirada"
    assert mensagens(publicador, "sonar/parada/demo/cmd")[-1] == {"acao": "desativar"}


def test_queda_do_sonar_ponto_e_da_camera(cliente, sonar):
    sonar.receber_mqtt("sonar/parada/demo/status", {"online": True, "rssi": -60})
    sonar.receber_mqtt("sonar/parada/demo/camera/status", {"online": True})
    espera_id = criar_espera(cliente)["id"]
    sonar.receber_mqtt("sonar/parada/demo/status", {"online": False})
    sonar.receber_mqtt("sonar/parada/demo/camera/status", {"online": False})
    sonar.cancelar_espera(espera_id)
    tipos = [e["tipo"] for e in ler_sse(cliente, f"/esperas/{espera_id}/eventos")]
    assert "ponto_offline" in tipos
    assert "sem_confirmacao_visual" in tipos
    texto = cliente.get("/metrics").text
    assert 'sonar_dispositivo_online{id="demo",tipo="ponto"} 0.0' in texto


def test_dispositivo_sem_sinal_vira_offline(sonar, cliente):
    sonar.receber_mqtt("sonar/onibus/90001/status", {"online": True})
    from sonar_api.db import Dispositivo

    with sonar._transacao() as (sessao, _saida):
        sessao.get(Dispositivo, "bordo:90001").ultimo_sinal_em = agora() - timedelta(minutes=5)
    sonar.verificar_temporizadores()
    painel = cliente.get("/painel/indicadores").json()
    assert {"tipo": "bordo", "id": "90001", "online": False} == {
        k: v for k, v in painel["dispositivos"][0].items() if k != "ultimo_sinal_em"
    }


def test_topico_estranho_e_ignorado(sonar):
    sonar.receber_mqtt("sonar/parada/../evento", {"linha_lida": "DEMO-10"})
    sonar.receber_mqtt("outro/qualquer/coisa/aqui", {})
    sonar.receber_mqtt("sonar/parada/nao-cadastrada/evento", {"linha_lida": "DEMO-10"})


def test_painel_conta_embarques_e_ocorrencias(cliente):
    primeira = criar_espera(cliente)["id"]
    segunda = criar_espera(cliente)["id"]
    cliente.post(f"/esperas/{primeira}/embarque", json={})
    cliente.post(f"/esperas/{segunda}/nao-parou", json={"consentimento": False})
    painel = cliente.get("/painel/indicadores").json()
    assert painel["esperas"] == 2
    assert painel["embarques"] == 1
    assert painel["nao_parou"] == 1
    assert painel["nao_parou_por_100_esperas"] == 50.0
    assert painel["ocorrencias_por_status"] == {"anonima": 1}
