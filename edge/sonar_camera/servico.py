"""Liga a câmera à espera: só processa quadros enquanto a API diz que há alguém esperando."""

import time
from collections.abc import Callable
from datetime import datetime, timezone

from .detectores import Detector
from .votacao import Votacao, casar_linha

Publicar = Callable[[str, dict, bool], None]


class ServicoCamera:
    def __init__(self, parada: str, detector: Detector, publicar: Publicar, linhas_da_parada: list[str], quadros: int = 3):
        self.parada = parada
        self.detector = detector
        self.publicar = publicar
        self.linhas_da_parada = [linha.upper() for linha in linhas_da_parada]
        self.votacao = Votacao(quadros=quadros)
        self.ativo = False
        self.linhas_alvo: list[str] = []
        self.topico_cmd = f"sonar/parada/{parada}/cmd"
        self.topico_visao = f"sonar/parada/{parada}/visao"
        self.topico_status = f"sonar/parada/{parada}/camera/status"

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

    def status(self, online: bool = True) -> None:
        self.publicar(self.topico_status, {"online": online, "ativa": self.ativo}, True)

    def passo(self) -> str | None:
        """Processa um quadro. Devolve a linha publicada, se houver."""
        if not self.ativo:
            return None
        melhor: tuple[str, float] | None = None
        for leitura in self.detector.ler():
            casada = casar_linha(leitura.texto, self.vocabulario())
            if casada:
                confianca = leitura.confianca * casada[1]
                if melhor is None or confianca > melhor[1]:
                    melhor = (casada[0], confianca)
        confirmada = self.votacao.adicionar(melhor[0] if melhor else None, melhor[1] if melhor else 0.0)
        if confirmada is None:
            return None
        linha, confianca = confirmada
        agora = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        self.publicar(self.topico_visao, {"linha_lida": linha, "confianca": confianca, "passou_em": agora}, False)
        return linha

    def rodar(self, parar: Callable[[], bool] = lambda: False, intervalo_status_s: float = 30.0) -> None:
        ultimo_status = 0.0
        while not parar():
            if time.monotonic() - ultimo_status > intervalo_status_s:
                self.status()
                ultimo_status = time.monotonic()
            self.passo()
            time.sleep(0.1 if self.ativo else 1.0)
