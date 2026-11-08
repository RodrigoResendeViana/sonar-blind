from fastapi import APIRouter, Depends, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.concurrency import run_in_threadpool

from ..servico import Sonar
from .comum import obter_sonar

router = APIRouter(tags=["saúde"])


@router.get("/healthz")
def healthz() -> dict:
    """Vivo. Usado pelo teste de fumaça do pipeline e pelo healthcheck do container."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request, sonar: Sonar = Depends(obter_sonar)) -> dict:
    await run_in_threadpool(sonar.verificar_banco)
    ponte = request.app.state.ponte
    return {
        "status": "ok",
        "olhovivo_configurado": sonar.olhovivo.configurado,
        "mqtt_conectado": ponte.conectado if ponte is not None else None,
        "ia_configurada": bool(sonar.cfg.ia_url),
    }


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
