"""Planejador de viagem: da posição do passageiro até o destino, com no máximo uma baldeação.

Pensado para quem não enxerga: além do tempo, pesa caminhada (mais cansativa e arriscada) e
baldeação (mais um ponto para achar). Os tempos são estimativas (distância pelo traçado da linha);
a previsão em tempo real do primeiro ônibus vem depois, do Olho Vivo.
"""

from dataclasses import dataclass

from .rede import PontoRede, Rede

VELOCIDADE_ONIBUS_MS = 5.0  # ~18 km/h no trânsito de São Paulo
VELOCIDADE_A_PE_MS = 1.0  # passo de quem caminha com bengala
PESO_CAMINHADA = 1.5
ESPERA_POR_TRECHO_S = 300
PENALIDADE_BALDEACAO_S = 420


@dataclass(frozen=True)
class Trecho:
    linha: str
    destino: str  # letreiro (sentido)
    embarque: PontoRede
    desembarque: PontoRede
    paradas: int  # quantas paradas depois do embarque
    distancia_m: float

    @property
    def minutos(self) -> int:
        return max(1, round(self.distancia_m / VELOCIDADE_ONIBUS_MS / 60))

    def como_dict(self) -> dict:
        return {
            "linha": self.linha,
            "sentido": self.destino,
            "embarque": {"id": self.embarque.id, "nome": self.embarque.nome, "lat": self.embarque.lat, "lon": self.embarque.lon},
            "desembarque": {
                "id": self.desembarque.id, "nome": self.desembarque.nome,
                "lat": self.desembarque.lat, "lon": self.desembarque.lon,
            },
            "paradas": self.paradas,
            "minutos": self.minutos,
        }


@dataclass(frozen=True)
class Plano:
    trechos: tuple[Trecho, ...]
    caminhada_inicio_m: float
    caminhada_fim_m: float
    custo_s: float

    @property
    def minutos(self) -> int:
        a_pe = (self.caminhada_inicio_m + self.caminhada_fim_m) / VELOCIDADE_A_PE_MS
        no_onibus = sum(t.distancia_m for t in self.trechos) / VELOCIDADE_ONIBUS_MS
        return max(1, round((a_pe + no_onibus + ESPERA_POR_TRECHO_S * len(self.trechos)) / 60))

    def como_dict(self) -> dict:
        return {
            "trechos": [t.como_dict() for t in self.trechos],
            "caminhada_inicio_m": round(self.caminhada_inicio_m),
            "caminhada_fim_m": round(self.caminhada_fim_m),
            "minutos_estimados": self.minutos,
            "baldeacoes": len(self.trechos) - 1,
        }


def _custo_caminhada(metros: float) -> float:
    return metros / VELOCIDADE_A_PE_MS * PESO_CAMINHADA


def planejar(
    rede: Rede,
    origens: list[tuple[PontoRede, float]],
    destinos: list[tuple[PontoRede, float]],
    maximo: int = 3,
) -> list[Plano]:
    """Melhores planos (mais baratos primeiro), sem repetir a mesma sequência de linhas."""
    chegada = {ponto.id: (ponto, metros) for ponto, metros in destinos}
    planos: list[Plano] = []

    # ida de um trecho só: a partir de cada ponto de origem, o que dá para alcançar sem baldear
    alcance: dict[str, tuple[float, Trecho, float]] = {}
    for origem, a_pe in origens:
        for indice, posicao in rede.por_ponto.get(origem.id, []):
            padrao, acumulado = rede.padroes[indice], rede.acumulado[indice]
            for adiante in range(posicao + 1, len(padrao.paradas)):
                ponto = rede.pontos[padrao.paradas[adiante]]
                distancia = acumulado[adiante] - acumulado[posicao]
                trecho = Trecho(padrao.linha, padrao.destino, origem, ponto, adiante - posicao, distancia)
                custo = _custo_caminhada(a_pe) + ESPERA_POR_TRECHO_S + distancia / VELOCIDADE_ONIBUS_MS
                if ponto.id in chegada:
                    destino, a_pe_fim = chegada[ponto.id]
                    planos.append(Plano((trecho,), a_pe, a_pe_fim, custo + _custo_caminhada(a_pe_fim)))
                if ponto.id not in alcance or custo < alcance[ponto.id][0]:
                    alcance[ponto.id] = (custo, trecho, a_pe)

    # segundo trecho: de cada ponto alcançado, uma linha que chegue a um ponto de destino
    for destino, a_pe_fim in destinos:
        for indice, posicao in rede.por_ponto.get(destino.id, []):
            padrao, acumulado = rede.padroes[indice], rede.acumulado[indice]
            for atras in range(posicao):
                baldeacao_id = padrao.paradas[atras]
                if baldeacao_id not in alcance:
                    continue
                custo_ate, primeiro, a_pe = alcance[baldeacao_id]
                if primeiro.linha == padrao.linha:
                    continue
                distancia = acumulado[posicao] - acumulado[atras]
                segundo = Trecho(padrao.linha, padrao.destino, rede.pontos[baldeacao_id], destino, posicao - atras, distancia)
                custo = (
                    custo_ate + PENALIDADE_BALDEACAO_S + ESPERA_POR_TRECHO_S + distancia / VELOCIDADE_ONIBUS_MS
                    + _custo_caminhada(a_pe_fim)
                )
                planos.append(Plano((primeiro, segundo), a_pe, a_pe_fim, custo))

    escolhidos: list[Plano] = []
    vistos: set[tuple[str, ...]] = set()
    for plano in sorted(planos, key=lambda p: p.custo_s):
        chave = tuple(t.linha for t in plano.trechos)
        if chave in vistos:
            continue
        vistos.add(chave)
        escolhidos.append(plano)
        if len(escolhidos) == maximo:
            break
    return escolhidos


# ------------------------------------------------------------------------------------- fala


def ponto_falado(nome: str) -> str:
    """'o ponto Praça Exemplo', mas 'o Ponto de demonstração' (sem repetir 'ponto'). Com 'n' na frente vira 'no ...'."""
    return f"o {nome}" if nome.strip().lower().startswith("ponto") else f"o ponto {nome}"


def metros_falados(metros: float) -> str:
    if metros < 30:
        return "aqui do lado"
    if metros < 1000:
        return f"a {round(metros / 10) * 10} metros"
    return f"a {metros / 1000:.1f} quilômetros".replace(".", ",")


def paradas_faladas(quantidade: int) -> str:
    return "na parada seguinte" if quantidade == 1 else f"{quantidade} paradas depois"


def descrever(plano: Plano, destino_nome: str) -> str:
    """O plano em frases curtas, para leitor de tela."""
    primeiro = plano.trechos[0]
    partes = [
        f"Para ir até {destino_nome}: {ponto_falado(primeiro.embarque.nome)} fica {metros_falados(plano.caminhada_inicio_m)}.",
        f"Pegue o {primeiro.linha}, sentido {primeiro.destino}, e desça n{ponto_falado(primeiro.desembarque.nome)}, "
        f"{paradas_faladas(primeiro.paradas)}.",
    ]
    if len(plano.trechos) > 1:
        segundo = plano.trechos[1]
        partes.append(
            f"Lá, pegue o {segundo.linha}, sentido {segundo.destino}, e desça n{ponto_falado(segundo.desembarque.nome)}, "
            f"{paradas_faladas(segundo.paradas)}."
        )
    if plano.caminhada_fim_m >= 30:
        partes.append(f"O destino fica {metros_falados(plano.caminhada_fim_m)} desse ponto.")
    partes.append(f"Ao todo, uns {plano.minutos} minutos.")
    return " ".join(partes)
