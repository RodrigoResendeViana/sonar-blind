from sonar_camera.detectores import Leitura
from sonar_camera.servico import ServicoCamera
from sonar_camera.votacao import Votacao, casar_linha


class Relogio:
    def __init__(self):
        self.agora = 0.0

    def __call__(self):
        return self.agora


class DetectorFixo:
    def __init__(self, leituras):
        self.leituras = leituras

    def ler(self):
        return list(self.leituras)


def test_casa_com_o_vocabulario_restrito():
    vocabulario = ["DEMO-10", "DEMO-20", "8000-10"]
    assert casar_linha("DEMO-10", vocabulario) == ("DEMO-10", 1.0)
    assert casar_linha("8000-10 TERM. LAPA", vocabulario) == ("8000-10", 0.95)
    assert casar_linha("DEM0-1O", vocabulario)[0] == "DEMO-10"  # OCR trocou O por 0
    assert casar_linha("PRAÇA DA SÉ", vocabulario) is None


def test_votacao_exige_quadros_seguidos_e_nao_repete():
    relogio = Relogio()
    votacao = Votacao(quadros=3, silencio_s=60, relogio=relogio)
    assert votacao.adicionar("DEMO-10", 0.9) is None
    assert votacao.adicionar("DEMO-20", 0.9) is None  # o letreiro piscou outro texto
    assert votacao.adicionar("DEMO-10", 0.9) is None
    assert votacao.adicionar("DEMO-10", 0.9) is None
    assert votacao.adicionar("DEMO-10", 0.6) == ("DEMO-10", 0.8)
    for _ in range(3):
        resultado = votacao.adicionar("DEMO-10", 0.9)
    assert resultado is None  # o mesmo ônibus continua parado
    relogio.agora = 120
    for _ in range(3):
        resultado = votacao.adicionar("DEMO-10", 0.9)
    assert resultado == ("DEMO-10", 0.9)


def test_so_processa_com_espera_ativa_e_publica_so_texto():
    publicadas = []
    servico = ServicoCamera(
        "demo",
        DetectorFixo([Leitura("DEMO-10 TERMINAL EXEMPLO", 0.9), Leitura("ruido", 0.99)]),
        lambda topico, dados, retido: publicadas.append((topico, dados, retido)),
        ["DEMO-10", "DEMO-20"],
    )
    for _ in range(3):
        assert servico.passo() is None  # sem espera: a câmera não processa nada
    servico.ao_comando({"acao": "ativar", "linhas_alvo": ["DEMO-10"]})
    resultados = [servico.passo() for _ in range(3)]
    assert resultados == [None, None, "DEMO-10"]
    topico, dados, retido = publicadas[-1]
    assert topico == "sonar/parada/demo/visao"
    assert set(dados) == {"linha_lida", "confianca", "passou_em"}
    assert retido is False
    servico.ao_comando({"acao": "desativar"})
    assert servico.passo() is None
