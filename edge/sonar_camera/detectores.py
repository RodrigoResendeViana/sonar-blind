"""Fontes de leitura do letreiro.

- Teclado: para testar sem câmera (digite a linha no terminal).
- Webcam: YOLO (modelo da equipe de Visão, treinado para achar o letreiro) + EasyOCR no recorte.
  As bibliotecas pesadas só são importadas neste modo. Nenhuma imagem sai do notebook.
"""

import queue
import sys
import threading
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Leitura:
    texto: str
    confianca: float
    # centro do letreiro no quadro, de 0 a 1 (0 = esquerda/topo). Vai para o braço do Maker Lab.
    x: float | None = None
    y: float | None = None


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


class DetectorWebcam:
    def __init__(self, camera: int = 0, modelo: str = "modelos/letreiro.pt", confianca_minima: float = 0.5):
        import cv2  # noqa: PLC0415 - dependência opcional
        import easyocr  # noqa: PLC0415
        from ultralytics import YOLO  # noqa: PLC0415

        self._captura = cv2.VideoCapture(camera)
        if not self._captura.isOpened():
            raise RuntimeError(f"não abri a câmera {camera}")
        self._yolo = YOLO(modelo)
        self._ocr = easyocr.Reader(["pt", "en"], gpu=False)
        self._minima = confianca_minima

    def ler(self) -> list[Leitura]:
        ok, quadro = self._captura.read()
        if not ok:
            return []
        altura, largura = quadro.shape[:2]
        leituras = []
        for caixa in self._yolo(quadro, verbose=False)[0].boxes:
            conf_caixa = float(caixa.conf)
            if conf_caixa < self._minima:
                continue
            x1, y1, x2, y2 = (int(v) for v in caixa.xyxy[0])
            for _pontos, texto, conf_texto in self._ocr.readtext(quadro[y1:y2, x1:x2]):
                leituras.append(
                    Leitura(texto, conf_caixa * float(conf_texto), (x1 + x2) / 2 / largura, (y1 + y2) / 2 / altura)
                )
        return leituras
