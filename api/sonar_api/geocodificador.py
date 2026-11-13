"""Endereço ou lugar falado → coordenadas, pelo Nominatim (OpenStreetMap).

Só é usado quando o destino não está entre os lugares conhecidos da rede. Regras de uso do
Nominatim público: no máximo 1 requisição por segundo, User-Agent identificando o app e cache.
A consulta sai do servidor (não do celular): o Nominatim vê o destino, mas não quem pediu.
"""

import asyncio
import logging
import time

import httpx

log = logging.getLogger("sonar.geocodificador")

# retângulo da Grande São Paulo (oeste, norte, leste, sul)
CAIXA_SP = "-46.98,-23.35,-46.30,-24.01"
AGENTE = "Sonar/1.0 (FIAP Global Solution; +https://github.com/RodrigoResendeViana/sonar-blind)"


class Geocodificador:
    def __init__(self, url: str = "https://nominatim.openstreetmap.org", transporte: httpx.AsyncBaseTransport | None = None):
        self._http = httpx.AsyncClient(
            base_url=url, timeout=6.0, transport=transporte, headers={"User-Agent": AGENTE, "Accept-Language": "pt-BR"}
        )
        self._cache: dict[str, list[dict]] = {}
        self._trava = asyncio.Lock()
        self._ultima = 0.0

    async def procurar(self, texto: str) -> list[dict]:
        """Até 3 resultados {nome, lat, lon}; lista vazia se não achar ou se o serviço falhar."""
        chave = texto.strip().lower()
        if chave in self._cache:
            return self._cache[chave]
        async with self._trava:
            espera = 1.1 - (time.monotonic() - self._ultima)
            if espera > 0:
                await asyncio.sleep(espera)
            try:
                resposta = await self._http.get(
                    "/search",
                    params={
                        "q": f"{texto}, São Paulo", "format": "jsonv2", "limit": 3, "countrycodes": "br",
                        "viewbox": CAIXA_SP, "bounded": 1,
                    },
                )
                resposta.raise_for_status()
                brutos = resposta.json()
            except (httpx.HTTPError, ValueError) as erro:
                log.warning("Nominatim falhou: %s", erro.__class__.__name__)
                return []
            finally:
                self._ultima = time.monotonic()
        resultados = [
            {"nome": (item.get("name") or item.get("display_name", "").split(",")[0]).strip(),
             "lat": float(item["lat"]), "lon": float(item["lon"])}
            for item in brutos
            if "lat" in item and "lon" in item
        ]
        if len(self._cache) > 500:
            self._cache.clear()
        self._cache[chave] = resultados
        return resultados

    async def fechar(self) -> None:
        await self._http.aclose()
