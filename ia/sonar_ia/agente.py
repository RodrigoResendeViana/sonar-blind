"""Ponto de troca da equipe de GenAI: substitua responder() pelo agente real."""

from typing import Literal

from pydantic import BaseModel, Field


class Pergunta(BaseModel):
    texto: str = Field(min_length=1, max_length=500)
    parada_id: str | None = Field(default=None, max_length=64)


class Resposta(BaseModel):
    status: Literal["ok", "nao_consta"]
    resposta_falada: str = Field(max_length=600)
    acao: dict | None = None
    fontes: list[str] = Field(default_factory=list)
    confianca: float = Field(default=0.0, ge=0.0, le=1.0)


def responder(pergunta: Pergunta) -> Resposta:
    """Esqueleto: sem fontes, não inventa nada."""
    return Resposta(
        status="nao_consta",
        resposta_falada="Ainda não sei responder isso. Pergunte sobre a linha que você quer pegar.",
    )
