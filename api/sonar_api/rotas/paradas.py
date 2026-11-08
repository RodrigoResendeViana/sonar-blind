from fastapi import APIRouter, Depends, HTTPException, Path, Query

from ..db import agora, iso
from ..olhovivo import OlhoVivoIndisponivel
from ..servico import NaoEncontrado, Sonar
from .comum import PADRAO_ID, obter_sonar

router = APIRouter(prefix="/paradas", tags=["paradas"])


@router.get("")
def listar(sonar: Sonar = Depends(obter_sonar)) -> list[dict]:
    return [parada.como_dict() for parada in sonar.paradas.todas()]


@router.get("/proxima")
def mais_proxima(
    lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180), sonar: Sonar = Depends(obter_sonar)
) -> dict:
    """A localização é usada só neste cálculo; ela não é gravada."""
    resultado = sonar.paradas.mais_proxima(lat, lon)
    if resultado is None:
        raise HTTPException(status_code=404, detail="nenhuma parada com coordenadas cadastradas")
    parada, distancia = resultado
    return {"parada": parada.como_dict(), "distancia_m": round(distancia)}


@router.get("/{parada_id}/previsao")
async def previsao(parada_id: str = Path(pattern=PADRAO_ID), sonar: Sonar = Depends(obter_sonar)) -> dict:
    try:
        veiculos = await sonar.previsao(parada_id)
    except NaoEncontrado as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro
    except OlhoVivoIndisponivel as erro:
        raise HTTPException(status_code=503, detail=str(erro)) from erro
    parada = sonar.paradas.obter(parada_id)
    return {
        "parada": parada.como_dict(),
        "fonte": "demonstracao" if parada.demo else "olhovivo",
        "veiculos": [v.como_dict() for v in veiculos],
        "atualizado_em": iso(agora()),
    }
