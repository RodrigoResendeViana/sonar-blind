from fastapi import FastAPI

from .agente import Pergunta, Resposta, responder

app = FastAPI(title="Sonar IA", docs_url="/docs")


@app.get("/healthz")
def saude() -> dict:
    return {"status": "ok"}


@app.post("/perguntar", response_model=Resposta)
def perguntar(pergunta: Pergunta) -> Resposta:
    return responder(pergunta)
