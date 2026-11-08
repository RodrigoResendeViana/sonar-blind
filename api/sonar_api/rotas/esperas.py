from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, Path, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ..seguranca import limitar
from ..servico import ENCERRAM_STREAM, Sonar
from .comum import CABECALHOS_SSE, PADRAO_ID, PADRAO_UUID, obter_sonar, stream_canal

router = APIRouter(prefix="/esperas", tags=["esperas"])

IdEspera = Path(pattern=PADRAO_UUID)


class NovaEspera(BaseModel):
    parada_id: str = Field(pattern=PADRAO_ID)
    linhas: list[str] = Field(min_length=1, max_length=5)
    origem: Literal["voz", "toque"] = "toque"
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)


class Embarque(BaseModel):
    origem: Literal["voz", "toque"] = "toque"
    horario: datetime | None = None


class NaoParou(BaseModel):
    consentimento: bool = Field(description="o usuário aceitou que o robô envie a reclamação")


@router.post("", status_code=201, dependencies=[Depends(limitar("esperas", 0.5))])
def criar(
    corpo: NovaEspera,
    sonar: Sonar = Depends(obter_sonar),
    x_sonar_usuario: str | None = Header(default=None, max_length=64),
) -> dict:
    """Usuário chegou ao ponto ("Cheguei"): liga o Sonar Ponto e começa a acompanhar as linhas."""
    return sonar.criar_espera(
        corpo.parada_id, corpo.linhas, corpo.origem, x_sonar_usuario, corpo.lat, corpo.lon, demo=False
    )


@router.get("/{espera_id}")
def obter(espera_id: str = IdEspera, sonar: Sonar = Depends(obter_sonar)) -> dict:
    return sonar.obter_espera(espera_id)


@router.post("/{espera_id}/localizar", dependencies=[Depends(limitar("localizar"))])
def localizar(espera_id: str = IdEspera, sonar: Sonar = Depends(obter_sonar)) -> dict:
    """Pede um bip ao Sonar Ponto para o usuário achar o poste."""
    return sonar.localizar(espera_id)


@router.post("/{espera_id}/embarque")
def embarque(corpo: Embarque, espera_id: str = IdEspera, sonar: Sonar = Depends(obter_sonar)) -> dict:
    """O usuário confirmou ("embarquei"); a API cruza com a passagem registrada pela câmera."""
    return sonar.confirmar_embarque(espera_id, corpo.origem, corpo.horario)


@router.post("/{espera_id}/nao-parou")
def nao_parou(corpo: NaoParou, espera_id: str = IdEspera, sonar: Sonar = Depends(obter_sonar)) -> dict:
    return sonar.registrar_nao_parou(espera_id, corpo.consentimento)


@router.post("/{espera_id}/cancelar")
def cancelar(espera_id: str = IdEspera, sonar: Sonar = Depends(obter_sonar)) -> dict:
    return sonar.cancelar_espera(espera_id)


@router.get("/{espera_id}/eventos")
async def eventos(
    request: Request,
    espera_id: str = IdEspera,
    last_event_id: str | None = Header(default=None),
    sonar: Sonar = Depends(obter_sonar),
) -> StreamingResponse:
    """Server-Sent Events da espera. Reenvia o que o cliente perdeu (Last-Event-ID)."""
    ultimo = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0
    canal = f"espera:{espera_id}"
    fila = sonar.barramento.inscrever(canal)  # antes do histórico, para não perder nada no meio
    try:
        estado, historico = await run_in_threadpool(sonar.eventos_desde, espera_id, ultimo)
    except Exception:
        sonar.barramento.cancelar(canal, fila)
        raise
    ja_enviados = {evento["id"] for evento in historico}

    def repetido(evento: dict) -> bool:
        id_evento = evento.get("id")
        return isinstance(id_evento, int) and (id_evento <= ultimo or id_evento in ja_enviados)

    async def deve_encerrar(evento: dict) -> bool:
        if evento.get("tipo") not in ENCERRAM_STREAM:
            return False
        return sonar.stream_encerrado(await run_in_threadpool(sonar.obter_espera, espera_id))

    iniciais = [{"tipo": "estado", "dados": estado}, *historico]
    corpo = stream_canal(
        request,
        sonar,
        canal,
        fila,
        iniciais,
        uma_vez=sonar.stream_encerrado(estado),
        ignorar=repetido,
        encerrar=deve_encerrar,
    )
    return StreamingResponse(corpo, media_type="text/event-stream", headers=CABECALHOS_SSE)
