import time

import pytest
from conftest import ler_sse
from fastapi.testclient import TestClient
from sonar_api.conversa import entender
from sonar_api.main import create_app
from test_planejador import _gtfs


class Conversa:
    """Fala com /conversa como o app faria, guardando a sessão."""

    def __init__(self, cliente, **extra):
        self.cliente, self.sessao, self.extra = cliente, None, extra

    def __call__(self, texto=None, evento="fala", **campos) -> dict:
        corpo = {"sessao": self.sessao, "evento": evento, "texto": texto, **self.extra, **campos}
        resposta = self.cliente.post("/conversa", json=corpo, headers={"X-Sonar-Usuario": "usuario-1"})
        assert resposta.status_code == 200, resposta.text
        dados = resposta.json()
        self.sessao = dados["sessao"]
        return dados


@pytest.mark.parametrize(
    ("frase", "esperado"),
    [
        ("Quero ir para o Hospital das Clínicas", ("destino", "hospital das clinicas", True)),
        ("me leva pro terminal", ("destino", "terminal", True)),
        ("quanto falta pra chegar no centro", ("quanto_falta", "centro", False)),
        ("ele não parou!", ("reclamar", None, False)),
        ("já estou no ônibus", ("embarquei", None, False)),
        ("sim", ("sim", None, False)),
        ("hospital", (None, None, False)),
    ],
)
def test_entender(frase, esperado):
    assert entender(frase) == esperado


def test_viagem_com_baldeacao_na_demonstracao(cliente):
    falar = Conversa(cliente, cenario_demo="maquete")
    assert "para onde você quer ir" in falar(evento="abrir")["fala"]

    plano = falar("quero ir para o hospital")
    assert plano["estado"] == "confirmar_plano" and plano["demo"] is True
    assert [t["linha"] for t in plano["plano"]["trechos"]] == ["DEMO-20", "DEMO-30"]
    assert "O próximo DEMO-20 chega em 3 minutos" in plano["fala"]

    assert falar("sim")["estado"] == "indo_ao_ponto"
    no_ponto = falar("cheguei")
    assert no_ponto["estado"] == "no_ponto" and no_ponto["espera_id"]
    espera = cliente.get(f"/esperas/{no_ponto['espera_id']}").json()
    assert espera["linhas"] == ["DEMO-20"] and espera["parada_id"] == "demo"

    a_bordo = falar("embarquei")
    assert a_bordo["estado"] == "a_bordo" and "Desça no ponto Centro (exemplo)" in a_bordo["fala"]
    time.sleep(0.35)  # viagem simulada (velocidade 100 nos testes)
    baldeacao = falar(evento="tick")
    assert "Agora vamos pegar o DEMO-30" in baldeacao["fala"]
    assert baldeacao["estado"] == "no_ponto" and baldeacao["trecho"] == 1
    assert cliente.get(f"/esperas/{baldeacao['espera_id']}").json()["parada_id"] == "ex-centro"

    falar("embarquei")
    time.sleep(0.35)
    fim = falar(evento="tick")
    assert fim["estado"] == "chegou" and "Hospital Exemplo" in fim["fala"]


def test_onibus_passou_direto_e_reclamacao_por_voz(cliente, sonar):
    falar = Conversa(cliente, cenario_demo="maquete")
    falar("quero ir para o terminal")
    falar("sim")
    espera_id = falar("cheguei")["espera_id"]
    sonar.processar_deteccao("demo", {"linha_lida": "DEMO-10", "confianca": 0.9, "tempo_parado_s": 0.4, "parou": False})

    reclamou = falar("sim")  # responde à pergunta "quer registrar uma reclamação?"
    assert reclamou["estado"] == "apos_ocorrencia" and "Registrei a reclamação" in reclamou["fala"]
    ocorrencia = cliente.get(f"/esperas/{espera_id}").json()["ocorrencia"]
    assert ocorrencia["consentimento"] is True and ocorrencia["status"] == "pendente"

    de_novo = falar("esperar de novo")
    assert de_novo["estado"] == "no_ponto" and de_novo["espera_id"] != espera_id


def test_cancelar_encerra_a_espera(cliente):
    falar = Conversa(cliente, cenario_demo="maquete")
    falar("me leva pro centro")
    falar("sim")
    espera_id = falar("cheguei")["espera_id"]
    assert falar("cancelar")["estado"] == "inicio"
    assert cliente.get(f"/esperas/{espera_id}").json()["status"] == "cancelada"


def test_pergunta_no_meio_da_espera_nao_troca_o_destino(cliente):
    falar = Conversa(cliente, cenario_demo="maquete")
    falar("quero ir para o terminal")
    falar("sim")
    falar("cheguei")
    resposta = falar("quanto falta pra chegar no terminal")
    assert resposta["estado"] == "no_ponto" and "DEMO-10" in resposta["fala"]


def test_destino_desconhecido_na_demonstracao(cliente):
    falar = Conversa(cliente)
    resposta = falar("quero ir para o aeroporto")
    assert resposta["estado"] == "inicio" and "dá para ir até" in resposta["fala"]


def test_comando_antes_do_destino(cliente):
    assert "Primeiro me diga para onde" in Conversa(cliente)("cheguei")["fala"]


def test_repetir_e_ajuda(cliente):
    falar = Conversa(cliente)
    primeira = falar("centro")["fala"]
    assert falar("repete")["fala"] == primeira
    assert "quero reclamar" in falar("ajuda")["fala"]


@pytest.fixture
def cliente_gtfs(cfg, publicador, tmp_path):
    cfg.gtfs_arquivo = str(_gtfs(tmp_path / "gtfs.zip"))
    cfg.geocodificador_url = ""
    app = create_app(cfg, publicador=publicador)
    with TestClient(app) as cliente:
        for _ in range(100):
            if app.state.redes.gtfs is not None:
                break
            time.sleep(0.02)
        yield cliente


def test_viagem_real_com_gps(cliente_gtfs):
    falar = Conversa(cliente_gtfs)
    pedido = falar("quero ir para o terminal lapa")
    assert pedido.get("pedir_localizacao") is True and pedido["repetir_texto"]

    plano = falar(pedido["repetir_texto"], lat=-23.5462, lon=-46.6380)
    assert plano["estado"] == "confirmar_plano" and plano["demo"] is False
    assert plano["plano"]["trechos"][0]["linha"] == "8000-10"

    indo = falar("sim")
    assert indo["estado"] == "indo_ao_ponto" and "130 metros" in indo["fala"]
    assert falar(evento="posicao", lat=-23.5458, lon=-46.6380)["estado"] == "indo_ao_ponto"
    chegou = falar(evento="posicao", lat=-23.5451, lon=-46.6380)  # ~10 m do ponto
    assert chegou["estado"] == "no_ponto" and "Você chegou ao ponto Praça Ramos de Azevedo" in chegou["fala"]
    espera = cliente_gtfs.get(f"/esperas/{chegou['espera_id']}").json()
    assert espera["parada_id"] == "sp-1001" and espera["linhas"] == ["8000-10"]

    falar("embarquei")
    assert "Prepare-se" in falar(evento="posicao", lat=-23.5240, lon=-46.7020)["fala"]
    fim = falar(evento="posicao", lat=-23.5231, lon=-46.7039)
    assert fim["estado"] == "chegou"


def test_planejar_sem_conversa(cliente):
    corpo = cliente.get("/viagens/planejar", params={"destino": "universidade"}).json()
    assert corpo["rede"] == "demonstracao"
    assert [t["linha"] for t in corpo["planos"][0]["trechos"]] == ["DEMO-20", "DEMO-30"]


def test_botao_do_ponto_avisa_todos_os_motoristas(cliente, sonar):
    primeira = cliente.post("/simulador/paradas/demo/botao").json()["espera"]
    assert primeira["linhas"] == ["DEMO-10", "DEMO-20"]
    segunda = cliente.post("/simulador/paradas/demo/botao").json()["espera"]
    assert segunda["id"] == primeira["id"]  # apertar de novo renova o mesmo pedido


def test_botao_pelo_mqtt(sonar, cliente):
    sonar.receber_mqtt("sonar/parada/demo/evento", {"tipo": "botao"})
    ativas = [e for e in cliente.get("/painel/indicadores").json()["por_linha"]]
    assert ativas  # a espera do botão entrou nas estatísticas


PASSAGEM_PAROU = {"linha_lida": "DEMO-20", "confianca": 0.93, "tempo_parado_s": 3.1, "parou": True}


def _ate_o_ponto(falar) -> dict:
    falar("quero ir para o hospital")
    falar("sim")
    return falar("cheguei")


def test_camera_do_celular_sem_o_sonar_ponto(cliente, sonar):
    sonar.receber_mqtt("sonar/parada/demo/camera/status", {"online": True, "ativa": False, "sem_ponto": True})
    no_ponto = _ate_o_ponto(Conversa(cliente))  # cenário automático
    assert "a câmera do ponto vai ler o letreiro" in no_ponto["fala"]
    time.sleep(0.8)  # o roteiro simulado já teria "trazido" os ônibus (velocidade 100): não pode rodar
    sonar.receber_mqtt("sonar/parada/demo/camera/passagem", PASSAGEM_PAROU)
    sonar.cancelar_espera(no_ponto["espera_id"])
    eventos = ler_sse(cliente, f"/esperas/{no_ponto['espera_id']}/eventos")
    chegando = [e for e in eventos if e["tipo"] == "onibus_chegando"]
    assert len(chegando) == 1 and "É o seu" in chegando[0]["fala"]
    assert chegando[0]["dados"]["origem"] == "camera"


def test_com_o_sonar_ponto_ligado_a_camera_nao_duplica(cliente, sonar):
    sonar.receber_mqtt("sonar/parada/demo/status", {"online": True})
    sonar.receber_mqtt("sonar/parada/demo/camera/status", {"online": True, "sem_ponto": True})
    no_ponto = _ate_o_ponto(Conversa(cliente, cenario_demo="maquete"))
    assert "Avisei o ponto: ele vai apitar" in no_ponto["fala"]
    sonar.receber_mqtt("sonar/parada/demo/camera/passagem", PASSAGEM_PAROU)
    sonar.cancelar_espera(no_ponto["espera_id"])
    tipos = [e["tipo"] for e in ler_sse(cliente, f"/esperas/{no_ponto['espera_id']}/eventos")]
    assert "onibus_chegando" not in tipos


def test_camera_comum_sem_ponto_mantem_o_roteiro_simulado(cliente, sonar):
    sonar.receber_mqtt("sonar/parada/demo/camera/status", {"online": True})  # sem "sem_ponto"
    no_ponto = _ate_o_ponto(Conversa(cliente))
    assert no_ponto["fala"].count("Avisei os motoristas que vêm para cá.") == 1
    assert "câmera" not in no_ponto["fala"]

