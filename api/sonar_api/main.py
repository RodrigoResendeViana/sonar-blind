"""Aplicação FastAPI.

Rodar com: uvicorn --factory sonar_api.main:create_app --root-path /api
(o Caddy publica a API em /api e repassa sem o prefixo).
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker
from starlette.concurrency import run_in_threadpool

from . import __version__, demo
from .barramento import Barramento
from .config import Settings
from .db import Base, criar_engine
from .metricas import HTTP_EM_ANDAMENTO, HTTP_LATENCIA, HTTP_REQUISICOES
from .mqtt_ponte import PonteMqtt, Publicador
from .olhovivo import ClienteOlhoVivo, OlhoVivoIndisponivel
from .paradas import CadastroParadas
from .rotas import esperas, ia, ocorrencias, painel, paradas, saude, simulador
from .servico import Conflito, NaoEncontrado, Sonar

log = logging.getLogger("sonar")


def _configurar_log() -> None:
    if not log.handlers:
        manipulador = logging.StreamHandler()
        manipulador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        log.addHandler(manipulador)
        log.setLevel(logging.INFO)
        log.propagate = False


async def monitorar(sonar: Sonar, intervalo: float) -> None:
    """Laço de fundo: temporizadores das esperas, previsão do Olho Vivo e sonda de disponibilidade."""
    ultima_consulta: dict[str, float] = {}
    ultima_sonda = 0.0
    while True:
        try:
            await run_in_threadpool(sonar.verificar_temporizadores)
            for parada_id in await run_in_threadpool(sonar.paradas_com_espera_real):
                if time.monotonic() - ultima_consulta.get(parada_id, 0.0) < 20:
                    continue
                ultima_consulta[parada_id] = time.monotonic()
                try:
                    veiculos = await sonar.previsao(parada_id)
                except OlhoVivoIndisponivel:
                    await run_in_threadpool(sonar.avisar_olhovivo_indisponivel, parada_id)
                    continue
                await run_in_threadpool(sonar.processar_previsao, parada_id, veiculos, False)
            codigo = sonar.paradas.codigo_sonda()
            if sonar.olhovivo.configurado and codigo and time.monotonic() - ultima_sonda > 60:
                ultima_sonda = time.monotonic()
                with suppress(OlhoVivoIndisponivel):
                    await sonar.olhovivo.previsao_parada(codigo)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("falha no monitor")
        await asyncio.sleep(intervalo)


def create_app(
    cfg: Settings | None = None,
    *,
    olhovivo: ClienteOlhoVivo | None = None,
    publicador: Publicador | None = None,
    transporte_http: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    _configurar_log()
    cfg = cfg or Settings()
    engine = criar_engine(cfg.database_url)
    Base.metadata.create_all(engine)
    sessoes = sessionmaker(engine, expire_on_commit=False)
    olhovivo = olhovivo or ClienteOlhoVivo(cfg.olhovivo_token, cfg.olhovivo_url, cfg.olhovivo_cache_s)
    sonar = Sonar(cfg, sessoes, CadastroParadas.carregar(cfg.paradas_arquivo), olhovivo, Barramento(), publicador)
    sonar.previsao_demo = demo.PREVISAO_INICIAL

    ponte = None
    if publicador is None and cfg.mqtt_host:
        ponte = PonteMqtt(cfg.mqtt_host, cfg.mqtt_port, cfg.mqtt_usuario, cfg.mqtt_senha, cfg.mqtt_tls, sonar.receber_mqtt)
        sonar.publicador = ponte
    elif publicador is None:
        log.warning("SONAR_MQTT_HOST não definido: sem hardware, só os simuladores")

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        await run_in_threadpool(sonar.carregar_metricas_dispositivos)
        if ponte is not None:
            ponte.iniciar()
        monitor = asyncio.create_task(monitorar(sonar, cfg.monitor_intervalo_s))
        try:
            yield
        finally:
            pendentes = [monitor, *app.state.tarefas]
            for tarefa in pendentes:
                tarefa.cancel()
            # espera as threads em andamento terminarem antes de fechar o banco
            await asyncio.gather(*pendentes, return_exceptions=True)
            if ponte is not None:
                ponte.parar()
            await olhovivo.fechar()
            await app.state.http.aclose()
            await run_in_threadpool(sonar.fechar, engine)

    app = FastAPI(
        title="API Sonar",
        version=__version__,
        description="Hub do Sonar: app de voz, Sonar Ponto, Sonar Bordo, IA e robô de ocorrências.",
        docs_url="/docs",
        redoc_url=None,
        lifespan=ciclo_de_vida,
    )
    app.state.cfg = cfg
    app.state.engine = engine
    app.state.sonar = sonar
    app.state.ponte = ponte
    app.state.http = httpx.AsyncClient(transport=transporte_http, timeout=cfg.ia_timeout_s)
    app.state.tarefas = set()
    app.state.limitadores = {}

    @app.middleware("http")
    async def medir(request: Request, call_next):
        if request.url.path.endswith("/eventos"):
            return await call_next(request)
        inicio = time.perf_counter()
        status = 500
        HTTP_EM_ANDAMENTO.inc()
        try:
            resposta = await call_next(request)
            status = resposta.status_code
            return resposta
        finally:
            HTTP_EM_ANDAMENTO.dec()
            rota = getattr(request.scope.get("route"), "path", "nao_encontrada")
            HTTP_REQUISICOES.labels(request.method, rota, str(status)).inc()
            HTTP_LATENCIA.labels(request.method, rota).observe(time.perf_counter() - inicio)

    @app.exception_handler(NaoEncontrado)
    async def _nao_encontrado(_request: Request, erro: NaoEncontrado):
        return JSONResponse(status_code=404, content={"detail": str(erro)})

    @app.exception_handler(Conflito)
    async def _conflito(_request: Request, erro: Conflito):
        return JSONResponse(status_code=409, content={"detail": str(erro)})

    @app.exception_handler(ValueError)
    async def _valor_invalido(_request: Request, erro: ValueError):
        return JSONResponse(status_code=422, content={"detail": str(erro)})

    for modulo in (saude, paradas, esperas, ia, painel, ocorrencias):
        app.include_router(modulo.router)
    if cfg.simuladores:
        app.include_router(simulador.router)
    return app
