"""Cliente da API Olho Vivo da SPTrans (v2.1), com cache de 30 s.

Documentação: https://www.sptrans.com.br/desenvolvedores/api-do-olho-vivo-guia-de-referencia/
O token fica só no Parameter Store; ele nunca entra no repositório nem na imagem.
"""

import asyncio
import time
from dataclasses import asdict, dataclass

import httpx

from .metricas import OLHOVIVO_CONFIGURADO, OLHOVIVO_DISPONIVEL, OLHOVIVO_LATENCIA, OLHOVIVO_REQUISICOES


class OlhoVivoIndisponivel(Exception):
    pass


@dataclass(frozen=True)
class Veiculo:
    linha: str
    destino: str
    prefixo: str
    minutos: int
    acessivel: bool | None = None
    previsto_para: str = ""

    def como_dict(self) -> dict:
        return asdict(self)


def _minutos_ate(hora_atual: str, hora_prevista: str) -> int:
    h1, m1 = (int(parte) for parte in hora_atual.split(":"))
    h2, m2 = (int(parte) for parte in hora_prevista.split(":"))
    diferenca = (h2 * 60 + m2) - (h1 * 60 + m1)
    if diferenca < -720:  # passou da meia-noite
        diferenca += 1440
    return max(diferenca, 0)


def interpretar_previsao(dados: dict | None) -> list[Veiculo]:
    """Converte a resposta de /Previsao/Parada numa lista ordenada por chegada.

    Campos usados: hr (hora da consulta), l[].c (letreiro), l[].lt0 (destino),
    l[].vs[].p (prefixo), t (previsão) e a (acessível).
    """
    if not dados or not dados.get("p"):
        return []
    hora_atual = dados["hr"]
    veiculos = []
    for linha in dados["p"].get("l") or []:
        for veiculo in linha.get("vs") or []:
            veiculos.append(
                Veiculo(
                    linha=str(linha["c"]).upper(),
                    destino=linha.get("lt0") or "",
                    prefixo=str(veiculo["p"]),
                    minutos=_minutos_ate(hora_atual, veiculo["t"]),
                    acessivel=veiculo.get("a"),
                    previsto_para=veiculo["t"],
                )
            )
    return sorted(veiculos, key=lambda v: v.minutos)


class ClienteOlhoVivo:
    def __init__(
        self,
        token: str,
        base_url: str = "https://api.olhovivo.sptrans.com.br/v2.1",
        cache_s: int = 30,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.token = token
        self.cache_s = cache_s
        self._cliente = httpx.AsyncClient(
            base_url=base_url,
            timeout=10.0,
            transport=transport,
            headers={"User-Agent": "sonar-fiap/0.1"},
        )
        self._autenticado = False
        self._cache: dict[int, tuple[float, list[Veiculo]]] = {}
        self._trava = asyncio.Lock()
        OLHOVIVO_CONFIGURADO.set(1 if token else 0)
        OLHOVIVO_DISPONIVEL.set(1 if token else 0)

    @property
    def configurado(self) -> bool:
        return bool(self.token)

    async def fechar(self) -> None:
        await self._cliente.aclose()

    async def _autenticar(self) -> None:
        resposta = await self._cliente.post("/Login/Autenticar", params={"token": self.token})
        resposta.raise_for_status()
        if resposta.json() is not True:
            raise OlhoVivoIndisponivel("o Olho Vivo recusou o token")
        self._autenticado = True

    async def _get(self, caminho: str, params: dict) -> dict:
        if not self._autenticado:
            await self._autenticar()
        resposta = await self._cliente.get(caminho, params=params)
        if resposta.status_code == 401:
            self._autenticado = False
            await self._autenticar()
            resposta = await self._cliente.get(caminho, params=params)
        resposta.raise_for_status()
        return resposta.json()

    async def previsao_parada(self, codigo_parada: int) -> list[Veiculo]:
        async with self._trava:
            instante = time.monotonic()
            em_cache = self._cache.get(codigo_parada)
            if em_cache and instante - em_cache[0] < self.cache_s:
                OLHOVIVO_REQUISICOES.labels("cache").inc()
                return em_cache[1]
            if not self.configurado:
                raise OlhoVivoIndisponivel("token do Olho Vivo não configurado")
            inicio = time.perf_counter()
            try:
                dados = await self._get("/Previsao/Parada", {"codigoParada": codigo_parada})
                veiculos = interpretar_previsao(dados)
            except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as erro:
                OLHOVIVO_REQUISICOES.labels("erro").inc()
                OLHOVIVO_DISPONIVEL.set(0)
                raise OlhoVivoIndisponivel(f"falha ao consultar o Olho Vivo: {erro.__class__.__name__}") from erro
            finally:
                OLHOVIVO_LATENCIA.observe(time.perf_counter() - inicio)
            OLHOVIVO_REQUISICOES.labels("ok").inc()
            OLHOVIVO_DISPONIVEL.set(1)
            self._cache[codigo_parada] = (instante, veiculos)
            return veiculos
