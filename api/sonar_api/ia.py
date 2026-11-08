"""Contrato da pergunta por voz (App -> API -> IA).

Se SONAR_IA_URL estiver definido, a pergunta vai para o agente da equipe de GenAI
(POST {SONAR_IA_URL}/perguntar, mesmo contrato). Sem ele, um responder por regras
mantém o MVP funcionando: só fala o que está no cadastro da parada e na previsão,
e diz "não consta" no resto.
"""

import re
import time
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from .metricas import IA_LATENCIA, IA_RESPOSTAS
from .olhovivo import OlhoVivoIndisponivel
from .paradas import normalizar_linha


class RespostaIA(BaseModel):
    status: Literal["ok", "nao_consta"]
    resposta_falada: str = Field(max_length=600)
    acao: dict | None = None
    fontes: list[str] = Field(default_factory=list)
    confianca: float = Field(default=0.0, ge=0.0, le=1.0)


_PADRAO_LINHA = re.compile(r"\b([0-9A-Za-z]{4})\s*([-–])?\s*([0-9]{2})\b")
_PADRAO_BASE = re.compile(r"\blinha\s+([0-9A-Za-z]{4})\b", re.IGNORECASE)


def extrair_linhas(texto: str, conhecidas: list[str]) -> list[str]:
    encontradas: list[str] = []
    for base, hifen, sufixo in _PADRAO_LINHA.findall(texto):
        codigo = normalizar_linha(f"{base}-{sufixo}")
        if codigo is None:
            continue
        plausivel = bool(hifen) or any(c.isdigit() for c in base) or codigo in conhecidas
        if plausivel and codigo not in encontradas:
            encontradas.append(codigo)
    if not encontradas:
        for base in _PADRAO_BASE.findall(texto):
            candidatas = [c for c in conhecidas if c.startswith(base.upper() + "-")]
            if len(candidatas) == 1:
                encontradas.append(candidatas[0])
    return encontradas


def _lista(itens: list[str]) -> str:
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


async def responder_por_regras(sonar, texto: str, parada_id: str | None) -> RespostaIA:
    parada = sonar.paradas.obter(parada_id) if parada_id and sonar.paradas.existe(parada_id) else None
    if parada is None:
        return RespostaIA(
            status="nao_consta",
            resposta_falada="Não sei em qual ponto você está. Ative a localização ou escolha o ponto na lista.",
        )
    linhas = extrair_linhas(texto, parada.codigos)
    fonte_parada = f"paradas:{parada.id}"
    if not linhas:
        if parada.codigos:
            return RespostaIA(
                status="nao_consta",
                resposta_falada=(
                    f"Não entendi qual linha você quer. No ponto {parada.nome} passam {_lista(parada.codigos)}. "
                    f"Diga, por exemplo: linha {parada.codigos[0]}."
                ),
                fontes=[fonte_parada],
                confianca=0.3,
            )
        return RespostaIA(
            status="nao_consta",
            resposta_falada="Não entendi qual linha você quer. Diga o número da linha, por exemplo: linha 8000-10.",
        )
    linha = linhas[0]
    if parada.codigos and linha not in parada.codigos:
        return RespostaIA(
            status="nao_consta",
            resposta_falada=f"Não consta a linha {linha} no ponto {parada.nome}.",
            fontes=[fonte_parada],
            confianca=0.8,
        )
    acao = {"tipo": "esperar", "parada_id": parada.id, "linhas": [linha]}
    try:
        veiculos = await sonar.previsao(parada.id)
    except OlhoVivoIndisponivel:
        return RespostaIA(
            status="ok",
            resposta_falada=(
                f"A previsão do Olho Vivo está indisponível agora. Posso esperar a linha {linha} com você "
                f"no ponto {parada.nome}."
            ),
            acao=acao,
            fontes=[fonte_parada],
            confianca=0.5,
        )
    fonte = "demonstracao:previsao" if parada.demo else f"olhovivo:previsao:{parada.codigo_sptrans}"
    origem = "Dados de demonstração." if parada.demo else "Fonte: Olho Vivo."
    proximos = [v for v in veiculos if v.linha == linha]
    if not proximos:
        return RespostaIA(
            status="ok",
            resposta_falada=f"Sem previsão agora para a linha {linha} no ponto {parada.nome}. Posso esperar com você.",
            acao=acao,
            fontes=[fonte],
            confianca=0.6,
        )
    veiculo = proximos[0]
    sentido = f", sentido {veiculo.destino}," if veiculo.destino else ""
    if veiculo.minutos <= 0:
        quando = "está chegando"
    elif veiculo.minutos == 1:
        quando = "chega em 1 minuto"
    else:
        quando = f"chega em {veiculo.minutos} minutos"
    return RespostaIA(
        status="ok",
        resposta_falada=f"A linha {linha}{sentido} {quando} no ponto {parada.nome}. {origem}",
        acao=acao,
        fontes=[fonte],
        confianca=0.9,
    )


async def _perguntar_servico(http: httpx.AsyncClient, url: str, timeout: float, texto: str, parada_id: str | None):
    try:
        resposta = await http.post(
            f"{url.rstrip('/')}/perguntar", json={"texto": texto, "parada_id": parada_id}, timeout=timeout
        )
        resposta.raise_for_status()
        return RespostaIA.model_validate(resposta.json())
    except (httpx.HTTPError, ValidationError, ValueError):
        return RespostaIA(
            status="nao_consta", resposta_falada="Não consegui responder agora. Tente de novo em instantes."
        )


async def perguntar(sonar, http: httpx.AsyncClient, texto: str, parada_id: str | None) -> RespostaIA:
    cfg = sonar.cfg
    modo = "servico" if cfg.ia_url else "regras"
    inicio = time.perf_counter()
    try:
        if cfg.ia_url:
            resposta = await _perguntar_servico(http, cfg.ia_url, cfg.ia_timeout_s, texto, parada_id)
        else:
            resposta = await responder_por_regras(sonar, texto, parada_id)
    finally:
        IA_LATENCIA.labels(modo).observe(time.perf_counter() - inicio)
    IA_RESPOSTAS.labels(modo, resposta.status).inc()
    return resposta
