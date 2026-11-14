"""Liga a câmera à espera: só processa quadros enquanto a API diz que há alguém esperando.

Com o Sonar Ponto, a câmera só publica a linha lida (`visao`) e o Ponto junta com o ultrassom.
Sem o Ponto (`sem_ponto`, ex.: a câmera do celular), a própria câmera faz o papel do ultrassom: o
letreiro na frente dela é o ônibus no ponto. Se o letreiro fica parado 3 s, ela avisa na hora que o
ônibus parou (dá tempo de embarcar); se ele some antes disso (atravessou o quadro), avisa que passou
direto. O aviso vai em `sonar/parada/{id}/camera/passagem`.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from .detectores import Detector, Leitura
from .votacao import Votacao, casar_linha

Publicar = Callable[[str, dict, bool], None]

PAROU_MIN_S = 3.0  # o mesmo limiar do Sonar Ponto e da API
AUSENCIA_S = 2.0  # sem letreiro por 2 s: o ônibus foi embora
TOLERANCIA_X = 0.08  # "parado": o letreiro não andou mais que 8% da largura do quadro


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class _Presenca:
    """Um ônibus na frente da câmera, quando ela trabalha sem o Sonar Ponto."""

    visto: float
    passou_em: str
    linha: str | None = None
    confianca: float = 0.0
    ancora_x: float | None = None
    ancora_t: float = 0.0
    parado_s: float = 0.0
    avisada: bool = False


class ServicoCamera:
    def __init__(
        self,
        parada: str,
        detector: Detector,
        publicar: Publicar,
        linhas_da_parada: list[str],
        quadros: int = 3,
        mirar_sempre: bool = False,
        sem_ponto: bool = False,
        relogio: Callable[[], float] = time.monotonic,
    ):
        self.parada = parada
        self.detector = detector
        self.publicar = publicar
        self.linhas_da_parada = [linha.upper() for linha in linhas_da_parada]
        self.votacao = Votacao(quadros=quadros, relogio=relogio)
        self.ativo = False
        self.linhas_alvo: list[str] = []
        self.topico_cmd = f"sonar/parada/{parada}/cmd"
        self.topico_visao = f"sonar/parada/{parada}/visao"
        self.topico_status = f"sonar/parada/{parada}/camera/status"
        self.topico_mira = f"sonar/parada/{parada}/mira"
        self.topico_passagem = f"sonar/parada/{parada}/camera/passagem"
        self.mirar_sempre = mirar_sempre  # para a demo do braço sem precisar abrir uma espera
        self.sem_ponto = sem_ponto  # a câmera avisa sozinha a chegada do ônibus
        self.relogio = relogio
        self._ultima_mira = -1e9
        self._alvo_visto_em = -1e9
        self._com_alvo = False
        self._presenca: _Presenca | None = None

    def vocabulario(self) -> list[str]:
        """Vocabulário restrito: as linhas da parada mais as esperadas agora."""
        return sorted(set(self.linhas_da_parada) | {linha.upper() for linha in self.linhas_alvo})

    def ao_comando(self, dados: dict) -> None:
        acao = dados.get("acao")
        if acao == "ativar":
            self.ativo = True
            self.linhas_alvo = [str(linha) for linha in dados.get("linhas_alvo") or []]
        elif acao == "desativar":
            self.ativo = False
            self.linhas_alvo = []
            self._presenca = None

    def status(self, online: bool = True) -> None:
        dados = {"online": online, "ativa": self.ativo}
        if self.sem_ponto:
            dados["sem_ponto"] = True  # a API passa a esperar a chegada do ônibus pela câmera
        self.publicar(self.topico_status, dados, True)

    def _mirar(self, alvo: tuple[float, float, str | None] | None) -> None:
        """Publica onde está o letreiro (no máximo ~7 vezes por segundo) para o braço seguir."""
        agora = self.relogio()
        if alvo is not None:
            self._alvo_visto_em = agora
            if agora - self._ultima_mira >= 0.15:
                x, y, linha = alvo
                self.publicar(self.topico_mira, {"alvo": True, "x": round(x, 3), "y": round(y, 3), "linha": linha}, False)
                self._ultima_mira = agora
                self._com_alvo = True
        elif self._com_alvo and agora - self._alvo_visto_em > 1.0:
            self.publicar(self.topico_mira, {"alvo": False}, False)
            self._com_alvo = False

    def passo(self) -> str | None:
        """Processa um quadro. Devolve a linha publicada, se houver."""
        if not self.ativo and not self.mirar_sempre:
            return None
        melhor: tuple[str, float] | None = None
        alvo: tuple[float, float, str | None] | None = None
        leitura_alvo: Leitura | None = None
        prioridade_alvo: tuple = (-1, False, 0.0)
        alvos_esperados = {linha.upper() for linha in self.linhas_alvo}
        for leitura in self.detector.ler():
            casada = casar_linha(leitura.texto, self.vocabulario())
            if casada and not leitura.rastreada:  # a votação só conta leituras novas do OCR
                confianca = leitura.confianca * casada[1]
                if melhor is None or confianca > melhor[1]:
                    melhor = (casada[0], confianca)
            if leitura.x is not None:
                # segue primeiro o ônibus esperado, depois qualquer linha conhecida, depois qualquer
                # letreiro; no empate, a leitura nova do OCR ganha da posição rastreada
                nivel = 2 if casada and casada[0] in alvos_esperados else 1 if casada else 0
                prioridade = (nivel, not leitura.rastreada, leitura.confianca)
                if prioridade > prioridade_alvo:
                    prioridade_alvo = prioridade
                    leitura_alvo = leitura
                    alvo = (leitura.x, leitura.y if leitura.y is not None else 0.5, casada[0] if casada else None)
        if leitura_alvo is not None and not leitura_alvo.rastreada and leitura_alvo.caixa is not None:
            seguir = getattr(self.detector, "seguir", None)
            if seguir is not None:
                seguir(leitura_alvo.caixa, alvo[2] or leitura_alvo.texto)
        self._mirar(alvo)
        if not self.ativo:
            return None
        confirmada = self.votacao.adicionar(melhor[0] if melhor else None, melhor[1] if melhor else 0.0)
        if self.sem_ponto:
            # posição de um letreiro de linha conhecida (leitura nova ou rastreada) neste quadro
            self._acompanhar(alvo[0] if alvo is not None and alvo[2] is not None else None, confirmada)
        if confirmada is None:
            return None
        linha, confianca = confirmada
        dados = {"linha_lida": linha, "confianca": confianca, "passou_em": _agora_iso()}
        self.publicar(self.topico_visao, dados, False)
        return linha

    # ------------------------------------------------------------------ sem o Sonar Ponto

    def _acompanhar(self, x: float | None, confirmada: tuple[str, float] | None) -> None:
        """Faz o papel do ultrassom: o letreiro na frente da câmera é o ônibus no ponto."""
        agora = self.relogio()
        presenca = self._presenca
        if presenca is not None and confirmada and presenca.linha and confirmada[0] != presenca.linha:
            self._encerrar(esquecer=False)  # outro letreiro na frente da câmera: é outro ônibus
            presenca = None
        if x is None and confirmada is None:
            if presenca is not None and agora - presenca.visto > AUSENCIA_S:
                self._encerrar()
            return
        if presenca is None:
            presenca = self._presenca = _Presenca(visto=agora, passou_em=_agora_iso(), ancora_x=x, ancora_t=agora)
        presenca.visto = agora
        if confirmada and presenca.linha is None:
            presenca.linha, presenca.confianca = confirmada
        if x is not None:
            if presenca.ancora_x is None or abs(x - presenca.ancora_x) > TOLERANCIA_X:
                presenca.ancora_x, presenca.ancora_t = x, agora  # o letreiro andou: recomeça a contar
            presenca.parado_s = max(presenca.parado_s, agora - presenca.ancora_t)
        if presenca.linha and not presenca.avisada and presenca.parado_s >= PAROU_MIN_S:
            self._avisar(presenca, parou=True)  # avisa já, com o ônibus ainda no ponto

    def _encerrar(self, esquecer: bool = True) -> None:
        presenca, self._presenca = self._presenca, None
        if esquecer:
            self.votacao.esquecer()  # se a mesma linha voltar, é outro ônibus
        if presenca is not None and presenca.linha and not presenca.avisada:
            self._avisar(presenca, parou=False)  # foi embora sem ficar parado: passou direto

    def _avisar(self, presenca: _Presenca, parou: bool) -> None:
        presenca.avisada = True
        self.publicar(
            self.topico_passagem,
            {
                "linha_lida": presenca.linha,
                "confianca": presenca.confianca,
                "tempo_parado_s": round(presenca.parado_s, 1),
                "parou": parou,
                "passou_em": presenca.passou_em,
            },
            False,
        )

    def rodar(self, parar: Callable[[], bool] = lambda: False, intervalo_status_s: float = 30.0) -> None:
        ultimo_status = 0.0
        while not parar():
            if time.monotonic() - ultimo_status > intervalo_status_s:
                self.status()
                ultimo_status = time.monotonic()
            self.passo()
            time.sleep(0.05 if self.ativo or self.mirar_sempre else 1.0)
