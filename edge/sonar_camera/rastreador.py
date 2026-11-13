"""Rastreia o letreiro entre uma detecção e outra.

O OCR (ou o YOLO) leva de 0,2 a 1,5 s por quadro numa CPU de notebook: rápido o bastante para ler
a linha, lento demais para o braço seguir um ônibus andando. Entre duas detecções, este rastreador
procura o recorte do letreiro no quadro novo (correlação normalizada, cv2.matchTemplate) numa janela
em volta da última posição. Custa poucos milissegundos por quadro.
"""

import numpy as np

Caixa = tuple[int, int, int, int]  # x1, y1, x2, y2 em pixels


def _cinza(quadro: np.ndarray) -> np.ndarray:
    import cv2  # noqa: PLC0415 - só no notebook com câmera

    return cv2.cvtColor(quadro, cv2.COLOR_BGR2GRAY) if quadro.ndim == 3 else quadro


class RastreadorModelo:
    def __init__(self, limiar: float = 0.55, margem: float = 1.0, falhas_max: int = 6, renovar_a_cada: int = 15):
        self.limiar = limiar
        self.margem = margem  # quanto da largura/altura do letreiro procurar em volta
        self.falhas_max = falhas_max
        self.renovar_a_cada = renovar_a_cada
        self.caixa: Caixa | None = None
        self.semelhanca = 0.0
        self._modelo: np.ndarray | None = None
        self._falhas = 0
        self._quadros = 0

    @property
    def ativo(self) -> bool:
        return self.caixa is not None

    def iniciar(self, quadro: np.ndarray, caixa: Caixa) -> bool:
        altura, largura = quadro.shape[:2]
        x1, y1, x2, y2 = max(0, caixa[0]), max(0, caixa[1]), min(largura, caixa[2]), min(altura, caixa[3])
        if x2 - x1 < 12 or y2 - y1 < 8:
            self.parar()
            return False
        self._modelo = _cinza(quadro)[y1:y2, x1:x2].copy()
        self.caixa = (x1, y1, x2, y2)
        self.semelhanca = 1.0
        self._falhas = 0
        self._quadros = 0
        return True

    def parar(self) -> None:
        self.caixa = None
        self._modelo = None
        self.semelhanca = 0.0

    def atualizar(self, quadro: np.ndarray) -> Caixa | None:
        """Nova posição do letreiro neste quadro (ou None se não achou desta vez)."""
        import cv2  # noqa: PLC0415

        if self.caixa is None or self._modelo is None:
            return None
        cinza = _cinza(quadro)
        altura, largura = cinza.shape[:2]
        x1, y1, x2, y2 = self.caixa
        w, h = x2 - x1, y2 - y1
        jx1, jy1 = max(0, int(x1 - self.margem * w)), max(0, int(y1 - self.margem * h))
        jx2, jy2 = min(largura, int(x2 + self.margem * w)), min(altura, int(y2 + self.margem * h))
        janela = cinza[jy1:jy2, jx1:jx2]
        mh, mw = self._modelo.shape[:2]
        if janela.shape[0] < mh or janela.shape[1] < mw:
            return self._falhou()
        resultado = cv2.matchTemplate(janela, self._modelo, cv2.TM_CCOEFF_NORMED)
        _minimo, maximo, _pos_min, (dx, dy) = cv2.minMaxLoc(resultado)
        if not np.isfinite(maximo) or maximo < self.limiar:
            return self._falhou()
        self.caixa = (jx1 + dx, jy1 + dy, jx1 + dx + mw, jy1 + dy + mh)
        self.semelhanca = float(maximo)
        self._falhas = 0
        self._quadros += 1
        if self._quadros % self.renovar_a_cada == 0 and maximo > 0.75:
            # renova o recorte aos poucos: o ônibus muda de ângulo e de luz enquanto chega
            nx1, ny1, nx2, ny2 = self.caixa
            self._modelo = cinza[ny1:ny2, nx1:nx2].copy()
        return self.caixa

    def _falhou(self) -> None:
        self._falhas += 1
        if self._falhas > self.falhas_max:
            self.parar()  # sumiu de vez: espera a próxima detecção
        return None
