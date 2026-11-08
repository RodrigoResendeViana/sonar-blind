"""Do texto lido no letreiro para uma linha confirmada.

O letreiro de LED pisca e alterna textos, e o OCR erra letras. Por isso:
1. o texto só vale se casar com o vocabulário restrito da parada (linhas que passam ali);
2. a linha só é confirmada quando N quadros seguidos concordam;
3. a mesma linha não é publicada de novo enquanto o ônibus está parado na frente.
"""

import difflib
import re
import time
from collections import deque
from collections.abc import Callable, Iterable


def _limpar(texto: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", texto.upper())


# trocas comuns do OCR em letreiro de LED (O/0, I/1, S/5...)
_CONFUSOES = str.maketrans("OQILSZB", "0011528")


def _canonico(texto: str) -> str:
    return _limpar(texto).translate(_CONFUSOES)


def casar_linha(texto: str, vocabulario: Iterable[str], corte: float = 0.75) -> tuple[str, float] | None:
    """Devolve (linha, semelhança) se o texto casar com alguma linha do vocabulário."""
    candidatas = {_limpar(linha): linha for linha in vocabulario}
    limpo = _limpar(texto)
    if not limpo or not candidatas:
        return None
    if limpo in candidatas:
        return candidatas[limpo], 1.0
    # o letreiro costuma trazer o número da linha e o destino juntos: procura a linha dentro do texto
    for chave, linha in candidatas.items():
        if chave and chave in limpo:
            return linha, 0.95
    canonicas = {_canonico(linha): linha for linha in candidatas.values()}
    if _canonico(limpo) in canonicas:
        return canonicas[_canonico(limpo)], 0.9
    parecidas = difflib.get_close_matches(limpo, list(candidatas), n=1, cutoff=corte)
    if parecidas:
        return candidatas[parecidas[0]], round(difflib.SequenceMatcher(None, limpo, parecidas[0]).ratio(), 3)
    return None


class Votacao:
    def __init__(self, quadros: int = 3, silencio_s: float = 60.0, relogio: Callable[[], float] = time.monotonic):
        self.quadros = quadros
        self.silencio_s = silencio_s
        self._relogio = relogio
        self._janela: deque[tuple[str | None, float]] = deque(maxlen=quadros)
        self._ultima: tuple[str, float] | None = None  # (linha, instante)

    def adicionar(self, linha: str | None, confianca: float) -> tuple[str, float] | None:
        """Registra o resultado de um quadro. Devolve (linha, confiança média) quando confirma."""
        self._janela.append((linha, confianca))
        if linha is None or len(self._janela) < self.quadros:
            return None
        if any(item[0] != linha for item in self._janela):
            return None
        media = round(sum(item[1] for item in self._janela) / self.quadros, 3)
        self._janela.clear()
        agora = self._relogio()
        if self._ultima and self._ultima[0] == linha and agora - self._ultima[1] < self.silencio_s:
            return None  # é o mesmo ônibus ainda parado na frente da câmera
        self._ultima = (linha, agora)
        return linha, media
