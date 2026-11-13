from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field

from ..planejador import descrever, planejar
from ..seguranca import limitar
from .comum import PADRAO_UUID

router = APIRouter(tags=["conversa por voz"])


class Fala(BaseModel):
    sessao: str | None = Field(default=None, pattern=PADRAO_UUID)
    evento: Literal["abrir", "fala", "posicao", "tick"] = "fala"
    texto: str | None = Field(default=None, max_length=300)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    cenario_demo: Literal["auto", "embarque", "nao_parou", "maquete"] = "auto"


@router.post("/conversa", dependencies=[Depends(limitar("conversa", 4))])
async def conversar(
    corpo: Fala, request: Request, x_sonar_usuario: str | None = Header(default=None, max_length=64)
) -> dict:
    """Um turno da conversa por voz. A localização (se vier) é usada e esquecida: não vai para o banco."""
    return await request.app.state.conversa.tratar(
        corpo.sessao, corpo.evento, corpo.texto, corpo.lat, corpo.lon, x_sonar_usuario, corpo.cenario_demo
    )


@router.get("/viagens/planejar", dependencies=[Depends(limitar("planejar", 1))])
async def planejar_viagem(
    request: Request,
    destino: str = Query(min_length=2, max_length=80, pattern=r"^[0-9A-Za-zÀ-ÿ .,'\-]+$"),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lon: float | None = Query(default=None, ge=-180, le=180),
) -> dict:
    """Plano de viagem sem conversa (usado pelo agente de IA e para testes)."""
    conversa = request.app.state.conversa
    sessao = type("Sessao", (), {"lat": lat, "lon": lon})()
    rede = conversa._escolher_rede(sessao, destino)
    if rede.fonte == "gtfs" and lat is None:
        rede = conversa.redes.demonstracao
    lugar = await conversa._resolver_destino(rede, destino)
    if lugar is None:
        return {"rede": rede.fonte, "destino": None, "planos": [], "fala": f"Não encontrei {destino}."}
    nome, dlat, dlon = lugar
    origens = conversa._origens(rede, sessao)
    destinos = rede.proximos(dlat, dlon, 600) or rede.proximos(dlat, dlon, 1000)
    planos = planejar(rede, origens, destinos)
    return {
        "rede": rede.fonte,
        "destino": nome,
        "planos": [p.como_dict() for p in planos],
        "fala": descrever(planos[0], nome) if planos else f"Não achei um caminho de ônibus até {nome}.",
    }
