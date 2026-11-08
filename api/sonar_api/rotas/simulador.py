"""Gêmeos digitais: o avaliador vê o ciclo inteiro no navegador, sem o hardware."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .. import demo
from ..seguranca import limitar
from ..servico import NaoEncontrado, Sonar
from .comum import CABECALHOS_SSE, PADRAO_ID, PADRAO_PREFIXO, PADRAO_UUID, obter_sonar, stream_canal

router = APIRouter(tags=["simuladores e demonstração"])

MAX_DEMOS_SIMULTANEAS = 20


class DeteccaoSimulada(BaseModel):
    linha_lida: str | None = Field(default=None, max_length=8)
    confianca: float = Field(default=0.9, ge=0, le=1)
    tempo_parado_s: float = Field(default=10.0, ge=0, le=600)
    parou: bool | None = None
    camera_ok: bool = True


class CienteSimulado(BaseModel):
    espera_id: str | None = Field(default=None, pattern=PADRAO_UUID)


class NovaDemo(BaseModel):
    cenario: Literal["embarque", "nao_parou", "maquete"] = "embarque"


@router.post("/simulador/paradas/{parada_id}/deteccao", dependencies=[Depends(limitar("simulador", 2))])
def deteccao(
    corpo: DeteccaoSimulada, parada_id: str = Path(pattern=PADRAO_ID), sonar: Sonar = Depends(obter_sonar)
) -> dict:
    """Publica uma detecção como se fosse a câmera e o ultrassom do Sonar Ponto."""
    if not sonar.paradas.existe(parada_id):
        raise NaoEncontrado("parada não encontrada")
    afetadas = sonar.processar_deteccao(parada_id, {**corpo.model_dump(), "origem": "simulador"})
    return {"esperas_afetadas": afetadas}


@router.post("/simulador/onibus/{prefixo}/ciente", dependencies=[Depends(limitar("simulador", 2))])
def ciente(corpo: CienteSimulado, prefixo: str = Path(pattern=PADRAO_PREFIXO), sonar: Sonar = Depends(obter_sonar)) -> dict:
    """O botão "Ciente" do Sonar Bordo simulado."""
    dados = {"simulado": True}
    if corpo.espera_id:
        dados["espera_id"] = corpo.espera_id
    return {"registrado": sonar.registrar_ciente(prefixo, dados)}


@router.get("/simulador/motorista/eventos")
async def eventos_motorista(request: Request, uma_vez: bool = False, sonar: Sonar = Depends(obter_sonar)):
    """Alertas para a tela do motorista simulado (todos os ônibus)."""
    fila = sonar.barramento.inscrever("motorista")
    iniciais = await run_in_threadpool(sonar.alertas_pendentes)
    corpo = stream_canal(request, sonar, "motorista", fila, iniciais, uma_vez=uma_vez)
    return StreamingResponse(corpo, media_type="text/event-stream", headers=CABECALHOS_SSE)


@router.get("/simulador/paradas/{parada_id}/eventos")
async def eventos_parada(
    request: Request, parada_id: str = Path(pattern=PADRAO_ID), uma_vez: bool = False, sonar: Sonar = Depends(obter_sonar)
):
    """Comandos e detecções de uma parada, para a tela do Sonar Ponto simulado."""
    canal = f"parada:{parada_id}"
    fila = sonar.barramento.inscrever(canal)
    try:
        estado = await run_in_threadpool(sonar.estado_parada, parada_id)
    except Exception:
        sonar.barramento.cancelar(canal, fila)
        raise
    corpo = stream_canal(request, sonar, canal, fila, [estado], uma_vez=uma_vez)
    return StreamingResponse(corpo, media_type="text/event-stream", headers=CABECALHOS_SSE)


@router.post("/demo/esperas", status_code=201, dependencies=[Depends(limitar("demo", 0.2))])
async def iniciar_demo(
    corpo: NovaDemo,
    request: Request,
    sonar: Sonar = Depends(obter_sonar),
    x_sonar_usuario: str | None = Header(default=None, max_length=64),
) -> dict:
    """Roda a jornada com dados de exemplo; o app acompanha pelo SSE como numa espera real."""
    tarefas: set[asyncio.Task] = request.app.state.tarefas
    if len(tarefas) >= MAX_DEMOS_SIMULTANEAS:
        raise HTTPException(status_code=429, detail="muitas demonstrações ao mesmo tempo; tente em instantes")
    sonar.previsao_demo = demo.PREVISAO_INICIAL
    espera = await run_in_threadpool(
        sonar.criar_espera, demo.PARADA_DEMO, [demo.LINHA_CERTA], "toque", x_sonar_usuario, None, None, True
    )
    tarefa = asyncio.create_task(demo.executar(sonar, espera["id"], corpo.cenario, sonar.cfg.demo_velocidade))
    tarefas.add(tarefa)
    tarefa.add_done_callback(tarefas.discard)
    return {**espera, "cenario": corpo.cenario}
