from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..seguranca import exigir_token_servico
from ..servico import Sonar
from .comum import obter_sonar

router = APIRouter(prefix="/ocorrencias", tags=["ocorrências (robô de RPA)"], dependencies=[Depends(exigir_token_servico)])


class AtualizacaoOcorrencia(BaseModel):
    status: Literal["em_processamento", "enviada", "inconclusiva", "duplicada", "erro"]
    protocolo: str | None = Field(default=None, max_length=64)
    mensagem: str | None = Field(default=None, max_length=1000)


@router.get("")
def listar(
    status: str | None = Query(default=None, max_length=32),
    limite: int = Query(default=100, ge=1, le=500),
    sonar: Sonar = Depends(obter_sonar),
) -> list[dict]:
    """O robô lê as pendentes (status=pendente) a cada 15 min."""
    return sonar.listar_ocorrencias(status, limite)


@router.patch("/{ocorrencia_id}")
def atualizar(ocorrencia_id: int, corpo: AtualizacaoOcorrencia, sonar: Sonar = Depends(obter_sonar)) -> dict:
    """O robô devolve o status e o protocolo; o app avisa o usuário."""
    return sonar.atualizar_ocorrencia(ocorrencia_id, corpo.status, corpo.protocolo, corpo.mensagem)
