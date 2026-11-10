"""Ferramentas do agente: só leitura, sempre pela API do Sonar (nunca direto no banco)."""

import re

import httpx

DEFINICOES = [
    {
        "type": "function",
        "function": {
            "name": "buscar_linha",
            "description": "Busca linhas de ônibus de São Paulo pelo número (ex.: 8000) ou por um lugar "
            "(ex.: Lapa, Terminal Pinheiros). Devolve código, origem e destino de cada sentido.",
            "parameters": {
                "type": "object",
                "properties": {"termo": {"type": "string", "description": "número da linha ou nome do lugar"}},
                "required": ["termo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "previsao_parada",
            "description": "Próximos ônibus de uma parada do Sonar: linha, destino e minutos até chegar.",
            "parameters": {
                "type": "object",
                "properties": {"parada_id": {"type": "string", "description": "id da parada, ex.: demo"}},
                "required": ["parada_id"],
            },
        },
    },
]

_TERMO = re.compile(r"^[0-9A-Za-zÀ-ÿ .\-]{2,40}$")
_ID = re.compile(r"^[a-z0-9-]{1,64}$")


class Ferramentas:
    def __init__(self, api: httpx.AsyncClient):
        self.api = api

    async def executar(self, nome: str, argumentos: dict) -> dict:
        try:
            if nome == "buscar_linha":
                return await self.buscar_linha(str(argumentos.get("termo", "")))
            if nome == "previsao_parada":
                return await self.previsao_parada(str(argumentos.get("parada_id", "")))
        except httpx.HTTPError:
            return {"erro": "dados indisponíveis agora"}
        return {"erro": f"ferramenta desconhecida: {nome}"}

    async def buscar_linha(self, termo: str) -> dict:
        termo = termo.strip()
        if not _TERMO.match(termo):
            return {"erro": "termo inválido"}
        resposta = await self.api.get("/linhas", params={"termo": termo})
        if resposta.status_code == 503:
            return {"erro": "Olho Vivo indisponível"}
        resposta.raise_for_status()
        corpo = resposta.json()
        linhas = [
            {"codigo": l["codigo"], "origem": l.get("origem", ""), "destino": l.get("destino", "")}
            for l in corpo["linhas"][:8]
        ]
        if not linhas:
            return {"linhas": [], "observacao": "nenhuma linha encontrada"}
        return {"linhas": linhas, "codigos": [l["codigo"] for l in linhas], "fonte": f"{corpo['fonte']}:linhas"}

    async def previsao_parada(self, parada_id: str) -> dict:
        if not _ID.match(parada_id):
            return {"erro": "parada inválida"}
        resposta = await self.api.get(f"/paradas/{parada_id}/previsao")
        if resposta.status_code in (404, 503):
            return {"erro": "previsão indisponível para essa parada"}
        resposta.raise_for_status()
        corpo = resposta.json()
        veiculos = [
            {"linha": v["linha"], "destino": v.get("destino", ""), "minutos": v["minutos"]}
            for v in corpo["veiculos"][:6]
        ]
        return {
            "parada": corpo["parada"]["nome"],
            "proximos": veiculos,
            "codigos": sorted({v["linha"] for v in veiculos}),
            "fonte": f"{corpo['fonte']}:previsao",
        }
