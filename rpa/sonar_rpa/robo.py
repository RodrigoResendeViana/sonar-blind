import httpx

from .portal import FalhaNoPortal, registrar

CAMPOS_OBRIGATORIOS = ("id", "linha")


def processar(cliente: httpx.Client, simular: bool = True) -> dict:
    """Uma rodada: lê as pendentes, registra e devolve o status para a API."""
    resumo = {"enviada": 0, "inconclusiva": 0, "erro": 0}
    pendentes = cliente.get("/ocorrencias", params={"status": "pendente"})
    pendentes.raise_for_status()
    for oc in pendentes.json():
        if any(not oc.get(c) for c in CAMPOS_OBRIGATORIOS):
            status, protocolo = "inconclusiva", None
        else:
            try:
                status, protocolo = "enviada", registrar(oc, simular=simular)
            except FalhaNoPortal:
                status, protocolo = "erro", None
        cliente.patch(f"/ocorrencias/{oc['id']}", json={"status": status, "protocolo": protocolo}).raise_for_status()
        resumo[status] += 1
    return resumo
