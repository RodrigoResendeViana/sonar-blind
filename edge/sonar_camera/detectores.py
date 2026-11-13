"""Fontes de leitura do letreiro.

- Teclado: para testar sem câmera (digite a linha no terminal).
- Câmera: acha o letreiro e lê o texto, de um destes jeitos:
  - "yolo": modelo da equipe de Visão (modelos/letreiro.pt) acha o letreiro e o OCR lê o recorte;
  - "ocr": sem modelo treinado, o próprio EasyOCR acha e lê os textos do quadro inteiro.
    Funciona bem com letreiro impresso na maquete; é o padrão enquanto o modelo não existe.
  Entre uma detecção e outra, um rastreador segue o letreiro para o braço do Maker Lab.

As bibliotecas pesadas (OpenCV, EasyOCR, Ultralytics) só são importadas no modo câmera.
Nenhuma imagem sai do notebook, e a câmera só fica aberta enquanto o serviço está lendo
(há uma espera ativa, ou a demonstração do braço com --mirar-sempre).
"""

import logging
import queue
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .rastreador import RastreadorModelo

log = logging.getLogger("sonar.camera")

CaixaNormalizada = tuple[float, float, float, float]  # x1, y1, x2, y2 de 0 a 1


@dataclass(frozen=True)
class Leitura:
    texto: str
    confianca: float
    # centro do letreiro no quadro, de 0 a 1 (0 = esquerda/topo). Vai para o braço do Maker Lab.
    x: float | None = None
    y: float | None = None
    caixa: CaixaNormalizada | None = None
    # True quando a posição veio do rastreador (não é uma leitura nova do OCR): serve para a mira,
    # mas não entra na votação da linha
    rastreada: bool = False


class Detector(Protocol):
    def ler(self) -> list[Leitura]:
        """Leituras do quadro atual (pode ser vazio)."""


class DetectorTeclado:
    """Cada linha digitada vira uma leitura repetida N vezes, para passar pela votação.

    "DEMO-10@0.2" simula o letreiro à esquerda do quadro (x = 0,2), para testar o braço sem câmera.
    """

    def __init__(self, quadros: int = 3, entrada=None):
        self._fila: queue.Queue[str] = queue.Queue()
        self._quadros = quadros
        self._pendentes: list[Leitura] = []
        entrada = entrada or sys.stdin
        threading.Thread(target=self._ler_entrada, args=(entrada,), daemon=True).start()

    def _ler_entrada(self, entrada) -> None:
        for linha in entrada:
            if linha.strip():
                self._fila.put(linha.strip())

    def ler(self) -> list[Leitura]:
        if not self._pendentes:
            try:
                texto = self._fila.get_nowait()
            except queue.Empty:
                return []
            texto, _, posicao = texto.partition("@")
            try:
                x = min(max(float(posicao), 0.0), 1.0) if posicao else 0.5
            except ValueError:
                x = 0.5
            self._pendentes = [Leitura(texto.strip(), 0.95, x, 0.5)] * self._quadros
        return [self._pendentes.pop()]


# ------------------------------------------------------------------------------------- localizadores

_TEXTO_UTIL = re.compile(r"[0-9A-Za-z]{2,}")
_PERMITIDOS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-./ "


def _leitura_da_caixa(texto: str, confianca: float, x1, y1, x2, y2, largura: int, altura: int) -> Leitura:
    caixa = (x1 / largura, y1 / altura, x2 / largura, y2 / altura)
    return Leitura(texto, confianca, (caixa[0] + caixa[2]) / 2, (caixa[1] + caixa[3]) / 2, caixa)


class LocalizadorOcr:
    """Sem modelo treinado: o EasyOCR acha e lê todos os textos do quadro."""

    nome = "ocr"

    def __init__(self, largura_max: int = 960, confianca_minima: float = 0.3):
        import easyocr  # noqa: PLC0415

        self._ocr = easyocr.Reader(["pt", "en"], gpu=False, verbose=False)
        self._largura_max = largura_max
        self._minima = confianca_minima

    def __call__(self, quadro) -> list[Leitura]:
        import cv2  # noqa: PLC0415

        altura, largura = quadro.shape[:2]
        escala = min(1.0, self._largura_max / largura)
        menor = cv2.resize(quadro, None, fx=escala, fy=escala) if escala < 1 else quadro
        leituras = []
        for pontos, texto, conf in self._ocr.readtext(menor, allowlist=_PERMITIDOS):
            if float(conf) < self._minima or not _TEXTO_UTIL.search(texto):
                continue
            xs = [p[0] / escala for p in pontos]
            ys = [p[1] / escala for p in pontos]
            leituras.append(_leitura_da_caixa(texto, float(conf), min(xs), min(ys), max(xs), max(ys), largura, altura))
        return leituras


class LocalizadorYolo:
    """Modelo da equipe de Visão acha o letreiro; o OCR lê só o recorte (mais rápido e mais preciso)."""

    nome = "yolo"

    def __init__(self, modelo: str, confianca_minima: float = 0.5):
        import easyocr  # noqa: PLC0415
        from ultralytics import YOLO  # noqa: PLC0415

        self._yolo = YOLO(modelo)
        self._ocr = easyocr.Reader(["pt", "en"], gpu=False, verbose=False)
        self._minima = confianca_minima

    def __call__(self, quadro) -> list[Leitura]:
        altura, largura = quadro.shape[:2]
        leituras = []
        for caixa in self._yolo(quadro, verbose=False)[0].boxes:
            conf_caixa = float(caixa.conf)
            if conf_caixa < self._minima:
                continue
            x1, y1, x2, y2 = (int(v) for v in caixa.xyxy[0])
            textos = [
                (texto, float(conf))
                for _pontos, texto, conf in self._ocr.readtext(quadro[y1:y2, x1:x2], allowlist=_PERMITIDOS)
            ]
            # o letreiro inteiro vira uma leitura só (número + destino), com a posição da caixa do YOLO
            texto = " ".join(t for t, _c in textos) or "?"
            conf_texto = max((c for _t, c in textos), default=0.0)
            leituras.append(_leitura_da_caixa(texto, conf_caixa * conf_texto, x1, y1, x2, y2, largura, altura))
        return leituras


def escolher_localizador(tipo: str, modelo: str):
    if tipo == "yolo" or (tipo == "auto" and Path(modelo).is_file()):
        log.info("detector: YOLO (%s) + OCR no recorte", modelo)
        return LocalizadorYolo(modelo)
    if tipo == "auto":
        log.warning("modelo %s não encontrado: usando só o OCR (funciona com letreiro impresso)", modelo)
    else:
        log.info("detector: OCR no quadro inteiro")
    return LocalizadorOcr()


# ------------------------------------------------------------------------------------- câmera


class DetectorCamera:
    """Lê a webcam em segundo plano: um fio captura e rastreia; outro detecta e lê o texto.

    ler() nunca espera o OCR: devolve as leituras novas (se houver) e a posição rastreada.
    """

    def __init__(self, localizador, camera: int = 0, janela: bool = False, ociosa_s: float = 10.0):
        self._localizador = localizador
        self._camera = camera
        self._janela = janela
        self._ociosa_s = ociosa_s
        self._trava = threading.Lock()
        self._captura = None
        self._quadro = None
        self._quadro_id = 0
        self._ultimo_ler = 0.0
        self._novas: list[Leitura] = []
        self._ultimas: list[Leitura] = []  # para desenhar na janela
        self._quadro_deteccao = None
        self._rastreador = RastreadorModelo()
        self._rotulo = ""
        self._parar = threading.Event()
        threading.Thread(target=self._capturar, daemon=True, name="captura").start()
        threading.Thread(target=self._detectar, daemon=True, name="deteccao").start()

    def _em_uso(self) -> bool:
        return time.monotonic() - self._ultimo_ler < self._ociosa_s

    def _capturar(self) -> None:
        import cv2  # noqa: PLC0415

        while not self._parar.is_set():
            if not self._em_uso():
                if self._captura is not None:
                    self._captura.release()  # ninguém esperando: a câmera desliga
                    self._captura = None
                    log.info("câmera desligada (sem espera ativa)")
                time.sleep(0.2)
                continue
            if self._captura is None:
                self._captura = cv2.VideoCapture(self._camera)
                if not self._captura.isOpened():
                    log.error("não abri a câmera %s; tento de novo em 5 s", self._camera)
                    self._captura = None
                    time.sleep(5)
                    continue
                log.info("câmera ligada")
            ok, quadro = self._captura.read()
            if not ok:
                time.sleep(0.05)
                continue
            with self._trava:
                self._quadro = quadro
                self._quadro_id += 1
                if self._rastreador.ativo:
                    self._rastreador.atualizar(quadro)

    def _detectar(self) -> None:
        ultimo_id = 0
        while not self._parar.is_set():
            with self._trava:
                quadro, quadro_id = self._quadro, self._quadro_id
            if quadro is None or quadro_id == ultimo_id or not self._em_uso():
                time.sleep(0.05)
                continue
            ultimo_id = quadro_id
            try:
                leituras = self._localizador(quadro)
            except Exception:  # noqa: BLE001 - um quadro ruim não pode derrubar o serviço
                log.exception("falha ao ler o quadro")
                continue
            with self._trava:
                self._novas.extend(leituras)
                self._ultimas = leituras
                self._quadro_deteccao = quadro

    def seguir(self, caixa: CaixaNormalizada, rotulo: str) -> None:
        """O serviço escolheu o alvo: o rastreador passa a seguir esta caixa."""
        with self._trava:
            quadro = self._quadro_deteccao if self._quadro_deteccao is not None else self._quadro
            if quadro is None:
                return
            altura, largura = quadro.shape[:2]
            pixels = (int(caixa[0] * largura), int(caixa[1] * altura), int(caixa[2] * largura), int(caixa[3] * altura))
            if self._rastreador.iniciar(quadro, pixels):
                self._rotulo = rotulo

    def ler(self) -> list[Leitura]:
        self._ultimo_ler = time.monotonic()
        with self._trava:
            leituras, self._novas = self._novas, []
            quadro = self._quadro
            caixa = self._rastreador.caixa
            semelhanca = self._rastreador.semelhanca
        if caixa is not None and quadro is not None:
            altura, largura = quadro.shape[:2]
            leituras.append(
                Leitura(
                    self._rotulo, semelhanca, (caixa[0] + caixa[2]) / 2 / largura, (caixa[1] + caixa[3]) / 2 / altura,
                    (caixa[0] / largura, caixa[1] / altura, caixa[2] / largura, caixa[3] / altura), rastreada=True,
                )
            )
        if self._janela and quadro is not None:
            self._mostrar(quadro.copy(), caixa)
        return leituras

    def _mostrar(self, quadro, caixa) -> None:
        """Janela de pré-visualização (para a demonstração e o vídeo). Só desenha; não grava nada."""
        import cv2  # noqa: PLC0415

        altura, largura = quadro.shape[:2]
        for leitura in self._ultimas:
            if leitura.caixa:
                x1, y1, x2, y2 = (int(v * d) for v, d in zip(leitura.caixa, (largura, altura, largura, altura)))
                cv2.rectangle(quadro, (x1, y1), (x2, y2), (0, 200, 255), 2)
                cv2.putText(quadro, leitura.texto[:24], (x1, max(15, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 2)
        if caixa is not None:
            cv2.rectangle(quadro, caixa[:2], caixa[2:], (0, 255, 0), 3)
            centro = ((caixa[0] + caixa[2]) // 2, (caixa[1] + caixa[3]) // 2)
            cv2.drawMarker(quadro, centro, (0, 255, 0), cv2.MARKER_CROSS, 24, 2)
        cv2.drawMarker(quadro, (largura // 2, altura // 2), (255, 255, 255), cv2.MARKER_TILTED_CROSS, 14, 1)
        legenda = f"{getattr(self._localizador, 'nome', '?')} | seguindo: {self._rotulo or '-'}"
        cv2.putText(quadro, legenda, (10, altura - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        try:
            cv2.imshow("Sonar - camera do ponto", quadro)
            cv2.waitKey(1)
        except cv2.error:
            log.warning("sem suporte a janela neste OpenCV (versão headless?); seguindo sem pré-visualização")
            self._janela = False

    def fechar(self) -> None:
        self._parar.set()
        if self._captura is not None:
            self._captura.release()
        if self._janela:
            import cv2  # noqa: PLC0415

            cv2.destroyAllWindows()
