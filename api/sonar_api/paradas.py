"""Cadastro das paradas com Sonar Ponto (arquivo JSON versionado no repositório)."""

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

PADRAO_ID = re.compile(r"^[a-z0-9-]{1,40}$")
PADRAO_LINHA = re.compile(r"^[0-9A-Z]{4}-[0-9]{2}$")


def normalizar_linha(valor: str | None) -> str | None:
    if not valor:
        return None
    texto = re.sub(r"\s+", "", str(valor)).upper().replace("–", "-")
    if re.fullmatch(r"[0-9A-Z]{4}[0-9]{2}", texto):
        texto = f"{texto[:4]}-{texto[4:]}"
    return texto if PADRAO_LINHA.fullmatch(texto) else None


@dataclass(frozen=True)
class Linha:
    codigo: str
    destino: str = ""


@dataclass(frozen=True)
class Parada:
    id: str
    nome: str
    codigo_sptrans: int | None = None
    lat: float | None = None
    lon: float | None = None
    demo: bool = False
    linhas: tuple[Linha, ...] = field(default_factory=tuple)

    @property
    def codigos(self) -> list[str]:
        return [linha.codigo for linha in self.linhas]

    def destino(self, codigo: str) -> str:
        for linha in self.linhas:
            if linha.codigo == codigo:
                return linha.destino
        return ""

    def como_dict(self) -> dict:
        return {
            "id": self.id,
            "nome": self.nome,
            "codigo_sptrans": self.codigo_sptrans,
            "lat": self.lat,
            "lon": self.lon,
            "demo": self.demo,
            "linhas": [{"codigo": linha.codigo, "destino": linha.destino} for linha in self.linhas],
        }


def distancia_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    raio = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * raio * math.asin(math.sqrt(a))


class CadastroParadas:
    def __init__(self, paradas: list[Parada]):
        self._paradas = {parada.id: parada for parada in paradas}

    @classmethod
    def carregar(cls, caminho: str = "") -> "CadastroParadas":
        arquivo = Path(caminho) if caminho else Path(__file__).parent / "dados" / "paradas.json"
        brutas = json.loads(arquivo.read_text(encoding="utf-8"))
        paradas = []
        for item in brutas:
            if not PADRAO_ID.fullmatch(item["id"]):
                raise ValueError(f"id de parada inválido: {item['id']!r}")
            linhas = []
            for linha in item.get("linhas", []):
                codigo = normalizar_linha(linha["codigo"])
                if codigo is None:
                    raise ValueError(f"código de linha inválido na parada {item['id']}: {linha['codigo']!r}")
                linhas.append(Linha(codigo, linha.get("destino", "")))
            paradas.append(
                Parada(
                    id=item["id"],
                    nome=item["nome"],
                    codigo_sptrans=item.get("codigo_sptrans"),
                    lat=item.get("lat"),
                    lon=item.get("lon"),
                    demo=bool(item.get("demo", False)),
                    linhas=tuple(linhas),
                )
            )
        return cls(paradas)

    def obter(self, parada_id: str) -> Parada:
        return self._paradas[parada_id]

    def existe(self, parada_id: str) -> bool:
        return parada_id in self._paradas

    def todas(self) -> list[Parada]:
        return list(self._paradas.values())

    def mais_proxima(self, lat: float, lon: float) -> tuple[Parada, float] | None:
        candidatas = [
            (parada, distancia_m(lat, lon, parada.lat, parada.lon))
            for parada in self._paradas.values()
            if parada.lat is not None and parada.lon is not None
        ]
        return min(candidatas, key=lambda item: item[1]) if candidatas else None

    def codigo_sonda(self) -> int | None:
        """Código de uma parada real, usado para medir se o Olho Vivo está no ar."""
        for parada in self._paradas.values():
            if parada.codigo_sptrans:
                return parada.codigo_sptrans
        return None
