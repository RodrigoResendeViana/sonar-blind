"""Gatilho do robô de RPA.

O n8n também lê as ocorrências pendentes a cada 15 minutos; o webhook só adianta o trabalho
para o passageiro ouvir o protocolo em segundos. Se o aviso falhar, nada se perde.
"""

import logging

import httpx

from .metricas import RPA_AVISOS

log = logging.getLogger("sonar.rpa")


def avisar_rpa(url: str, ocorrencia_id: int) -> None:
    """Roda em segundo plano, depois da resposta ao app. Só manda o id: o robô busca o resto na API."""
    try:
        httpx.post(url, json={"ocorrencia_id": ocorrencia_id}, timeout=3.0).raise_for_status()
        RPA_AVISOS.labels("ok").inc()
    except httpx.HTTPError as erro:
        RPA_AVISOS.labels("erro").inc()
        log.warning("não consegui avisar o robô de RPA (%s); ele pega a ocorrência na próxima rodada", erro.__class__.__name__)
