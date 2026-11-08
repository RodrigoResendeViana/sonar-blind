def test_healthz(cliente):
    resposta = cliente.get("/healthz")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_readyz_sem_broker(cliente):
    corpo = cliente.get("/readyz").json()
    assert corpo["status"] == "ok"
    assert corpo["mqtt_conectado"] is None
    assert corpo["olhovivo_configurado"] is False


def test_metrics_tem_os_sinais_de_ouro(cliente):
    cliente.get("/healthz")
    texto = cliente.get("/metrics").text
    assert 'sonar_http_requisicoes_total{metodo="GET",rota="/healthz",status="200"}' in texto
    assert "sonar_http_latencia_segundos_bucket" in texto
    assert "sonar_olhovivo_disponivel" in texto
    assert "sonar_esperas_ativas" in texto


def test_rota_inexistente_nao_cria_serie_nova(cliente):
    cliente.get("/rota/que/nao/existe/123")
    texto = cliente.get("/metrics").text
    assert 'rota="nao_encontrada"' in texto
    assert "/rota/que/nao/existe/123" not in texto
