from fastapi import APIRouter, Depends, HTTPException, Query

from ..olhovivo import OlhoVivoIndisponivel
from ..servico import Sonar
from .comum import obter_sonar

router = APIRouter(prefix="/linhas", tags=["linhas"])


@router.get("")
async def buscar(
    termo: str = Query(min_length=2, max_length=40, pattern=r"^[0-9A-Za-zÀ-ÿ .\-]+$"),
    sonar: Sonar = Depends(obter_sonar),
) -> dict:
    """Busca de linha por número ou destino (usada pelo agente de IA). Fonte: Olho Vivo."""
    try:
        fonte, linhas = await sonar.buscar_linhas(termo)
    except OlhoVivoIndisponivel as erro:
        raise HTTPException(status_code=503, detail=str(erro)) from erro
    return {"fonte": fonte, "linhas": linhas}
