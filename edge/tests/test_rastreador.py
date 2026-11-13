import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from sonar_camera.detectores import Leitura  # noqa: E402
from sonar_camera.rastreador import RastreadorModelo  # noqa: E402
from sonar_camera.servico import ServicoCamera  # noqa: E402


def _letreiro() -> np.ndarray:
    gerador = np.random.default_rng(1)
    return (gerador.random((24, 60)) * 255).astype(np.uint8)


def _quadro(x: int, y: int, com_letreiro: bool = True) -> np.ndarray:
    gerador = np.random.default_rng(7)
    quadro = (gerador.random((240, 320)) * 60).astype(np.uint8)
    if com_letreiro:
        quadro[y : y + 24, x : x + 60] = _letreiro()
    return cv2.cvtColor(quadro, cv2.COLOR_GRAY2BGR)


def test_segue_o_letreiro_andando():
    rastreador = RastreadorModelo()
    assert rastreador.iniciar(_quadro(100, 80), (100, 80, 160, 104))
    for passo in range(1, 6):
        caixa = rastreador.atualizar(_quadro(100 + 12 * passo, 80 + passo))
    assert caixa == (160, 85, 220, 109)
    assert rastreador.semelhanca > 0.9


def test_desiste_quando_o_letreiro_some():
    rastreador = RastreadorModelo(falhas_max=2)
    rastreador.iniciar(_quadro(100, 80), (100, 80, 160, 104))
    for _ in range(3):
        assert rastreador.atualizar(_quadro(0, 0, com_letreiro=False)) is None
    assert not rastreador.ativo


def test_caixa_pequena_demais_nao_rastreia():
    assert not RastreadorModelo().iniciar(_quadro(100, 80), (100, 80, 105, 84))


class DetectorComRastreio:
    def __init__(self, leituras):
        self.leituras = leituras
        self.seguindo = []

    def ler(self):
        return list(self.leituras)

    def seguir(self, caixa, rotulo):
        self.seguindo.append((caixa, rotulo))


def test_posicao_rastreada_vai_para_a_mira_mas_nao_para_a_votacao():
    rastreada = Leitura("DEMO-10", 0.9, 0.7, 0.5, (0.6, 0.4, 0.8, 0.6), rastreada=True)
    detector = DetectorComRastreio([rastreada])
    publicados = []
    servico = ServicoCamera("demo", detector, lambda t, d, r: publicados.append((t, d)), ["DEMO-10"])
    servico.ao_comando({"acao": "ativar", "linhas_alvo": ["DEMO-10"]})
    for _ in range(5):
        assert servico.passo() is None  # o rastreador repete o rótulo; isso não confirma a linha
    assert [d for t, d in publicados if t.endswith("/mira")][0]["x"] == 0.7
    assert detector.seguindo == []  # já está seguindo; não reinicia


def test_leitura_nova_do_ocr_vira_alvo_do_rastreador():
    nova = Leitura("8000-10 TERM LAPA", 0.8, 0.3, 0.5, (0.2, 0.4, 0.4, 0.6))
    detector = DetectorComRastreio([nova])
    servico = ServicoCamera("demo", detector, lambda t, d, r: None, ["8000-10"], mirar_sempre=True)
    servico.passo()
    assert detector.seguindo == [((0.2, 0.4, 0.4, 0.6), "8000-10")]


class CameraFalsa:
    """Imita o cv2.VideoCapture: o letreiro anda 4 px para a direita a cada quadro."""

    def __init__(self, _indice):
        self.x = 60

    def isOpened(self):
        return True

    def read(self):
        import time

        time.sleep(0.01)
        self.x = min(self.x + 4, 240)
        return True, _quadro(self.x, 100)

    def release(self):
        pass


def test_camera_detecta_rastreia_e_desliga_sozinha(monkeypatch):
    import time

    from sonar_camera.detectores import DetectorCamera

    monkeypatch.setattr(cv2, "VideoCapture", CameraFalsa)
    chamadas = []

    def localizador(quadro):
        chamadas.append(1)
        if len(chamadas) > 1:
            time.sleep(0.5)  # o OCR é lento; o rastreador cobre o intervalo
            return []
        x = int(np.argmax(quadro[112, :, 0] > 70))  # acha o letreiro no quadro falso
        return [Leitura("DEMO-10", 0.9, None, None, (x / 320, 100 / 240, (x + 60) / 320, 124 / 240))]

    detector = DetectorCamera(localizador, ociosa_s=0.5)
    try:
        leituras = []
        for _ in range(100):
            leituras = detector.ler()
            if leituras:
                break
            time.sleep(0.02)
        nova = leituras[0]
        assert not nova.rastreada
        detector.seguir(nova.caixa, "DEMO-10")
        time.sleep(0.3)
        rastreada = [leitura for leitura in detector.ler() if leitura.rastreada][0]
        assert rastreada.texto == "DEMO-10"
        assert rastreada.x > (nova.caixa[0] + nova.caixa[2]) / 2 + 0.05  # o letreiro andou e o rastreador foi junto
        time.sleep(1.0)  # ninguém lendo: a câmera desliga
        assert detector._captura is None
    finally:
        detector.fechar()
