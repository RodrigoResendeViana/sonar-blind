"""Rede de ônibus usada pelo planejador de viagem.

Duas fontes, com a mesma estrutura:
- demonstração (dados/rede_demo.json): poucas linhas fictícias em volta da maquete, com uma
  baldeação; funciona sem nada configurado e em qualquer lugar;
- GTFS da SPTrans (SONAR_GTFS_ARQUIVO): todas as linhas e paradas de São Paulo. O stop_id do GTFS
  é o mesmo código de parada do Olho Vivo, então a previsão em tempo real casa com o plano.

Cada linha vira um ou mais "padrões" (linha + sentido + sequência de paradas).
"""

import csv
import io
import json
import logging
import math
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .paradas import distancia_m

log = logging.getLogger("sonar.rede")

# abreviações comuns nos nomes da SPTrans
ABREVIACOES = {
    "term": "terminal", "pca": "praca", "av": "avenida", "r": "rua", "jd": "jardim", "vl": "vila",
    "pq": "parque", "sto": "santo", "sta": "santa", "hosp": "hospital", "univ": "universidade",
    "est": "estacao", "estac": "estacao", "cid": "cidade", "con": "conjunto", "cj": "conjunto",
    "pte": "ponte", "lgo": "largo", "dr": "doutor", "prof": "professor", "pres": "presidente",
    "mal": "marechal", "eng": "engenheiro", "gal": "general", "cptm": "cptm", "metro": "metro",
}
PALAVRAS_VAZIAS = {
    "de", "da", "do", "das", "dos", "o", "a", "os", "as", "e", "para", "pra", "pro", "ao", "aos",
    "em", "no", "na", "nos", "nas", "um", "uma", "ate", "perto", "proximo", "proxima", "exemplo",
    "sp", "sao", "paulo",
}


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", (texto or "").lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^a-z0-9 ]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


_MINUSCULAS = {"de", "da", "do", "das", "dos", "e", "a", "o", "x"}
_SIGLAS = {"usp", "cptm", "sesc", "senai", "fmu", "uni", "ceu", "ubs", "ama", "hc", "sp", "cdhu", "fiap"}


def nome_falado(nome: str) -> str:
    """'PCA. RAMOS DE AZEVEDO' → 'Praça Ramos de Azevedo': o leitor de tela lê direito."""
    nome = (nome or "").strip()
    if not nome or not nome.isupper():
        return nome
    palavras = []
    for indice, palavra in enumerate(nome.split()):
        base = palavra.rstrip(".").lower()
        if palavra.endswith(".") and base in ABREVIACOES:
            palavra = ABREVIACOES[base]
            palavra = palavra.upper() if palavra in ("cptm",) else palavra.capitalize()
        elif base in _SIGLAS:
            palavra = palavra.upper()
        elif indice and base in _MINUSCULAS:
            palavra = palavra.lower()
        else:
            palavra = palavra.capitalize()
        palavras.append(palavra)
    texto = " ".join(palavras)
    return texto.replace("Praca", "Praça").replace("Estacao", "Estação").replace("Sao ", "São ").replace("Metro", "Metrô")


def termos(texto: str) -> list[str]:
    """Palavras que importam, com as abreviações da SPTrans por extenso."""
    return [ABREVIACOES.get(p, p) for p in normalizar(texto).split() if p not in PALAVRAS_VAZIAS]


@dataclass(frozen=True)
class PontoRede:
    id: str
    nome: str
    lat: float
    lon: float
    codigo_sptrans: int | None = None


@dataclass(frozen=True)
class Padrao:
    linha: str
    destino: str
    paradas: tuple[str, ...]


@dataclass(frozen=True)
class Lugar:
    nome: str
    lat: float
    lon: float
    apelidos: tuple[str, ...] = ()


@dataclass
class Rede:
    fonte: str  # "demonstracao" ou "gtfs"
    pontos: dict[str, PontoRede]
    padroes: list[Padrao]
    lugares: list[Lugar] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.por_ponto: dict[str, list[tuple[int, int]]] = {}
        self.acumulado: list[list[float]] = []
        for indice, padrao in enumerate(self.padroes):
            distancias = [0.0]
            for anterior, atual in zip(padrao.paradas, padrao.paradas[1:]):
                a, b = self.pontos[anterior], self.pontos[atual]
                distancias.append(distancias[-1] + distancia_m(a.lat, a.lon, b.lat, b.lon))
            self.acumulado.append(distancias)
            for posicao, ponto_id in enumerate(padrao.paradas):
                self.por_ponto.setdefault(ponto_id, []).append((indice, posicao))
        # grade de ~1 km para achar paradas perto sem varrer as 20 mil
        self._grade: dict[tuple[int, int], list[PontoRede]] = {}
        for ponto in self.pontos.values():
            self._grade.setdefault(self._celula(ponto.lat, ponto.lon), []).append(ponto)
        self._termos_lugar = [(lugar, [set(termos(n)) for n in (lugar.nome, *lugar.apelidos)]) for lugar in self.lugares]

    @staticmethod
    def _celula(lat: float, lon: float) -> tuple[int, int]:
        return (math.floor(lat * 100), math.floor(lon * 100))

    def proximos(self, lat: float, lon: float, raio_m: float = 600, limite: int = 8) -> list[tuple[PontoRede, float]]:
        """Paradas que têm linha, até raio_m metros, da mais perto para a mais longe."""
        cel_lat, cel_lon = self._celula(lat, lon)
        alcance = max(1, math.ceil(raio_m / 1000))
        achados = []
        for dlat in range(-alcance, alcance + 1):
            for dlon in range(-alcance, alcance + 1):
                for ponto in self._grade.get((cel_lat + dlat, cel_lon + dlon), []):
                    if ponto.id not in self.por_ponto:
                        continue
                    distancia = distancia_m(lat, lon, ponto.lat, ponto.lon)
                    if distancia <= raio_m:
                        achados.append((ponto, distancia))
        return sorted(achados, key=lambda item: item[1])[:limite]

    def mais_proximo(self, lat: float, lon: float) -> tuple[PontoRede, float] | None:
        perto = self.proximos(lat, lon, raio_m=3000, limite=1)
        return perto[0] if perto else None

    def linhas_no_ponto(self, ponto_id: str) -> list[tuple[str, str]]:
        vistas: dict[str, str] = {}
        for indice, posicao in self.por_ponto.get(ponto_id, []):
            padrao = self.padroes[indice]
            if posicao < len(padrao.paradas) - 1:  # no ponto final a linha não sai mais para esse lado
                vistas.setdefault(padrao.linha, padrao.destino)
        return sorted(vistas.items())

    def procurar_lugar(self, texto: str, minimo: float = 0.6) -> list[tuple[Lugar, float]]:
        """Lugares conhecidos da rede pelo nome ou apelido (sem acento, com abreviações)."""
        procurados = set(termos(texto))
        if not procurados:
            return []
        achados = []
        for lugar, variantes in self._termos_lugar:
            melhor = 0.0
            for variante in variantes:
                if not variante:
                    continue
                comuns = len(procurados & variante)
                # quanto do que a pessoa falou aparece no nome, e quanto do nome ela falou
                nota = 0.7 * comuns / len(procurados) + 0.3 * comuns / len(variante)
                melhor = max(melhor, nota)
            if melhor >= minimo:
                achados.append((lugar, melhor))
        return sorted(achados, key=lambda item: -item[1])


# ------------------------------------------------------------------------------------- fontes


def carregar_demo(caminho: str = "") -> Rede:
    arquivo = Path(caminho) if caminho else Path(__file__).parent / "dados" / "rede_demo.json"
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    pontos = {p["id"]: PontoRede(p["id"], p["nome"], p["lat"], p["lon"]) for p in dados["pontos"]}
    padroes = []
    for linha in dados["linhas"]:
        padroes.append(Padrao(linha["codigo"], linha["destino"], tuple(linha["ida"])))
        if linha.get("volta_destino"):
            padroes.append(Padrao(linha["codigo"], linha["volta_destino"], tuple(reversed(linha["ida"]))))
    lugares = [Lugar(l["nome"], l["lat"], l["lon"], tuple(l.get("apelidos", []))) for l in dados["lugares"]]
    return Rede("demonstracao", pontos, padroes, lugares)


def _ler_csv(arquivo_zip: zipfile.ZipFile, nome: str):
    with arquivo_zip.open(nome) as bruto:
        yield from csv.DictReader(io.TextIOWrapper(bruto, encoding="utf-8-sig"))


def carregar_gtfs(caminho: str) -> Rede:
    """Lê o GTFS (zip) e guarda um padrão por linha e sentido: a viagem com mais paradas."""
    with zipfile.ZipFile(caminho) as arquivo:
        pontos: dict[str, PontoRede] = {}
        for linha in _ler_csv(arquivo, "stops.txt"):
            stop_id = linha["stop_id"].strip()
            if not linha.get("stop_lat") or not linha.get("stop_lon"):
                continue
            codigo = int(stop_id) if stop_id.isdigit() else None
            pontos[stop_id] = PontoRede(
                stop_id, nome_falado(linha.get("stop_name", "")), float(linha["stop_lat"]), float(linha["stop_lon"]), codigo
            )
        rotas = {r["route_id"]: (r.get("route_short_name") or r["route_id"]).strip() for r in _ler_csv(arquivo, "routes.txt")}
        viagens: dict[str, tuple[str, str, str]] = {}
        for viagem in _ler_csv(arquivo, "trips.txt"):
            chave = (viagem["route_id"], viagem.get("direction_id", "0"))
            viagens[viagem["trip_id"]] = (*chave, nome_falado(viagem.get("trip_headsign") or ""))
        sequencias: dict[str, list[tuple[int, str]]] = {}
        for parada in _ler_csv(arquivo, "stop_times.txt"):
            if parada["trip_id"] in viagens and parada["stop_id"] in pontos:
                sequencias.setdefault(parada["trip_id"], []).append((int(parada["stop_sequence"]), parada["stop_id"]))

    melhores: dict[tuple[str, str], tuple[str, list[str]]] = {}
    for trip_id, sequencia in sequencias.items():
        route_id, sentido, destino = viagens[trip_id]
        paradas = [stop for _ordem, stop in sorted(sequencia)]
        atual = melhores.get((route_id, sentido))
        if atual is None or len(paradas) > len(atual[1]):
            melhores[(route_id, sentido)] = (destino, paradas)
    padroes = [
        Padrao(rotas.get(route_id, route_id), destino, tuple(paradas))
        for (route_id, _sentido), (destino, paradas) in melhores.items()
        if len(paradas) >= 2
    ]
    # cada destino de letreiro vira um lugar (ex.: "TERM. LAPA" no último ponto da linha)
    lugares: dict[str, Lugar] = {}
    for padrao in padroes:
        if padrao.destino and padrao.destino not in lugares:
            fim = pontos[padrao.paradas[-1]]
            lugares[padrao.destino] = Lugar(padrao.destino, fim.lat, fim.lon)
    log.info("GTFS carregado: %d paradas, %d padrões de linha", len(pontos), len(padroes))
    return Rede("gtfs", pontos, padroes, list(lugares.values()))
