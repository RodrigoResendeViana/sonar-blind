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


def _servico(leituras, relogio, **extra):
    publicados = []
    servico = ServicoCamera(
        "demo", DetectorFixo(leituras), lambda t, d, r: publicados.append((t, d)), ["DEMO-10", "DEMO-20"],
        relogio=relogio, **extra,
    )
    return servico, publicados


def _miras(publicados):
    return [dados for topico, dados in publicados if topico.endswith("/mira")]


def test_mira_segue_o_onibus_esperado():
    relogio = Relogio()
    leituras = [Leitura("DEMO-20", 0.99, 0.1, 0.5), Leitura("DEMO-10", 0.7, 0.8, 0.4)]
    servico, publicados = _servico(leituras, relogio)
    servico.ao_comando({"acao": "ativar", "linhas_alvo": ["DEMO-10"]})
    servico.passo()
    assert _miras(publicados) == [{"alvo": True, "x": 0.8, "y": 0.4, "linha": "DEMO-10"}]


def test_mira_limita_a_frequencia_e_avisa_quando_perde_o_alvo():
    relogio = Relogio()
    detector_leituras = [Leitura("DEMO-10", 0.9, 0.5, 0.5)]
    servico, publicados = _servico(detector_leituras, relogio, mirar_sempre=True)
    servico.passo()
    relogio.agora = 0.05
    servico.passo()  # cedo demais: não publica de novo
    assert len(_miras(publicados)) == 1
    servico.detector.leituras = []
    relogio.agora = 0.5
    servico.passo()  # sumiu há pouco: ainda não desiste
    relogio.agora = 1.6
    servico.passo()
    assert _miras(publicados)[-1] == {"alvo": False}


def test_sem_espera_e_sem_mirar_sempre_nao_publica_nada():
    servico, publicados = _servico([Leitura("DEMO-10", 0.9, 0.5, 0.5)], Relogio())
    servico.passo()
    assert publicados == []


def test_mirar_sempre_nao_confirma_linha_sem_espera():
    servico, publicados = _servico([Leitura("DEMO-10", 0.9, 0.5, 0.5)], Relogio(), mirar_sempre=True)
    for _ in range(5):
        servico.passo()
    assert not [d for t, d in publicados if t.endswith("/visao")]
