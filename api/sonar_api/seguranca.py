"""Limite de requisições, token do robô de RPA e hash do usuário anônimo."""

import hashlib
import secrets
import threading
import time
from collections import deque

from fastapi import Header, HTTPException, Request


class LimitadorTaxa:
    """Janela deslizante de 60 s por chave (IP do cliente, vindo do Caddy)."""

    def __init__(self, por_minuto: int):
        self.por_minuto = por_minuto
        self._janelas: dict[str, deque] = {}
        self._trava = threading.Lock()

    def permitir(self, chave: str) -> bool:
        instante = time.monotonic()
        with self._trava:
            janela = self._janelas.setdefault(chave, deque())
            while janela and instante - janela[0] > 60:
                janela.popleft()
            if len(janela) >= self.por_minuto:
                return False
            janela.append(instante)
            if len(self._janelas) > 10_000:
                for antiga in [c for c, j in self._janelas.items() if not j or instante - j[-1] > 60]:
                    del self._janelas[antiga]
            return True


def limitar(nome: str, fator: float = 1.0):
    """Dependência do FastAPI: 429 quando o cliente passa do limite."""

    def dependencia(request: Request) -> None:
        limitadores: dict[str, LimitadorTaxa] = request.app.state.limitadores
        if nome not in limitadores:
            limite = max(1, int(request.app.state.cfg.limite_por_minuto * fator))
            limitadores[nome] = LimitadorTaxa(limite)
        cliente = request.client.host if request.client else "desconhecido"
        if not limitadores[nome].permitir(cliente):
            raise HTTPException(status_code=429, detail="muitas requisições; tente de novo em um minuto")

    return dependencia


def exigir_token_servico(request: Request, authorization: str | None = Header(default=None)) -> None:
    """Protege as rotas usadas pelo robô de RPA."""
    esperado = request.app.state.cfg.token_servico
    if not esperado:
        raise HTTPException(status_code=503, detail="token de serviço não configurado")
    recebido = (authorization or "").encode()
    if not secrets.compare_digest(recebido, f"Bearer {esperado}".encode()):
        raise HTTPException(status_code=401, detail="token inválido")


def hash_usuario(sal: str, usuario: str | None) -> str | None:
    """O id anônimo gerado no celular vira SHA-256 com sal; o id original nunca é gravado."""
    if not usuario:
        return None
    return hashlib.sha256(f"{sal}:{usuario}".encode()).hexdigest()
