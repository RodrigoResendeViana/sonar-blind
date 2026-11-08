from fastapi import APIRouter, Depends, Query

from ..servico import Sonar
from .comum import obter_sonar

router = APIRouter(prefix="/painel", tags=["painel da cidade"])


@router.get("/indicadores")
def indicadores(
    dias: int = Query(default=30, ge=1, le=365),
    incluir_demo: bool = True,
    sonar: Sonar = Depends(obter_sonar),
) -> dict:
    """Esperas, avisos confirmados e ônibus que não pararam. Só números agregados, sem dado pessoal."""
    return sonar.indicadores(dias, incluir_demo)
