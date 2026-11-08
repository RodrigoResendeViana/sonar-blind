import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import Request

from ..metricas import SSE_CONEXOES
from ..servico import Sonar

PADRAO_ID = r"^[a-z0-9-]{1,40}$"
PADRAO_PREFIXO = r"^[A-Za-z0-9-]{1,40}$"
PADRAO_UUID = r"^[0-9a-f-]{36}$"

CABECALHOS_SSE = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def obter_sonar(request: Request) -> Sonar:
    return request.app.state.sonar


def formatar_sse(evento: dict) -> str:
    """Eventos com "id" numérico levam o campo id do SSE, que o navegador devolve no Last-Event-ID."""
    texto = json.dumps(evento, ensure_ascii=False, separators=(",", ":"))
    id_evento = evento.get("id")
    cabecalho = f"id: {id_evento}\n" if isinstance(id_evento, int) else ""
    return f"{cabecalho}data: {texto}\n\n"


async def stream_canal(
    request: Request,
    sonar: Sonar,
    canal: str,
    fila: asyncio.Queue,
    iniciais: list[dict],
    uma_vez: bool = False,
    ignorar: Callable[[dict], bool] | None = None,
    encerrar: Callable[[dict], Awaitable[bool]] | None = None,
) -> AsyncIterator[str]:
    """Envia os eventos iniciais e depois os ao vivo, com ping a cada 15 s."""
    SSE_CONEXOES.inc()
    try:
        yield "retry: 3000\n\n"
        for evento in iniciais:
            yield formatar_sse(evento)
        if uma_vez:
            return
        while True:
            try:
                evento = await asyncio.wait_for(fila.get(), timeout=15)
            except TimeoutError:
                if await request.is_disconnected():
                    return
                yield ": ping\n\n"
                continue
            if ignorar is not None and ignorar(evento):
                continue
            yield formatar_sse(evento)
            if encerrar is not None and await encerrar(evento):
                return
    finally:
        sonar.barramento.cancelar(canal, fila)
        SSE_CONEXOES.dec()
