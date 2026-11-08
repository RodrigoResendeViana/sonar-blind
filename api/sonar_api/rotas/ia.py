from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ..ia import RespostaIA, perguntar
from ..seguranca import limitar
from ..servico import Sonar
from .comum import PADRAO_ID, obter_sonar

router = APIRouter(prefix="/ia", tags=["ia"])


class Pergunta(BaseModel):
    texto: str = Field(min_length=1, max_length=500)
    parada_id: str | None = Field(default=None, pattern=PADRAO_ID)


@router.post("/perguntar", response_model=RespostaIA, dependencies=[Depends(limitar("ia", 0.5))])
async def perguntar_rota(corpo: Pergunta, request: Request, sonar: Sonar = Depends(obter_sonar)) -> RespostaIA:
    """Entra texto e parada_id; sai status, resposta_falada, acao, fontes e confianca."""
    return await perguntar(sonar, request.app.state.http, corpo.texto, corpo.parada_id)
