import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request

from .agente import Agente, Pergunta, Resposta
from .ferramentas import Ferramentas


def criar_app(ollama: httpx.AsyncClient | None = None, api: httpx.AsyncClient | None = None) -> FastAPI:
    @asynccontextmanager
    async def ciclo(app: FastAPI):
        cliente_ollama = ollama or httpx.AsyncClient(
            base_url=os.getenv("SONAR_OLLAMA_URL", "http://ollama:11434"), timeout=18.0
        )
        cliente_api = api or httpx.AsyncClient(base_url=os.getenv("SONAR_API_URL", "http://api:8000"), timeout=5.0)
        app.state.agente = Agente(cliente_ollama, Ferramentas(cliente_api), os.getenv("SONAR_IA_MODELO", "qwen2.5:3b"))
        yield
        await cliente_ollama.aclose()
        await cliente_api.aclose()

    app = FastAPI(title="Sonar IA", lifespan=ciclo, docs_url="/docs")

    @app.get("/healthz")
    def saude() -> dict:
        return {"status": "ok"}

    @app.post("/perguntar", response_model=Resposta)
    async def perguntar(pergunta: Pergunta, request: Request) -> Resposta:
        return await request.app.state.agente.responder(pergunta)

    return app


app = criar_app()
