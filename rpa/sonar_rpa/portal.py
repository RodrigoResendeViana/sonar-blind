"""Ponto de troca da equipe de RPA: registrar a reclamação no canal oficial."""

import uuid


class FalhaNoPortal(Exception):
    pass


def registrar(ocorrencia: dict, simular: bool = True) -> str:
    """Devolve o protocolo. Sem automação real ainda, só o modo simulado funciona."""
    if simular:
        return f"SIM-{uuid.uuid4().hex[:8].upper()}"
    raise FalhaNoPortal("automação do portal ainda não implementada")
