"""Avaliação do agente de IA, para o relatório de GenAI.

    python avaliar.py                                   # contra https://sonar.rodrigoviana.app.br/api
    python avaliar.py --api http://localhost/api        # contra o compose local
    python avaliar.py --com-olhovivo                    # inclui as perguntas que precisam do token

Faz cada pergunta de avaliacao/perguntas.json pela API pública (o mesmo caminho do app), confere
com o esperado e escreve avaliacao/resultado.md (tabela pronta para o relatório) e resultado.json.
Respeita o limite de requisições da API (uma pergunta a cada ~5 s).
"""

import argparse
import json
import statistics
import time
from pathlib import Path

import httpx

PASTA = Path(__file__).parent / "avaliacao"


def conferir(esperado: dict, corpo: dict) -> list[str]:
    """Devolve a lista de critérios que falharam (vazia = acertou)."""
    falhas = []
    texto = corpo.get("resposta_falada", "")
    texto_min = texto.casefold()
    acao = corpo.get("acao") or {}
    linhas_acao = acao.get("linhas") or []
    if "status" in esperado and corpo.get("status") not in esperado["status"]:
        falhas.append(f"status {corpo.get('status')}")
    for trecho in esperado.get("contem", []):
        if trecho.casefold() not in texto_min:
            falhas.append(f"faltou '{trecho}'")
    if esperado.get("contem_algum") and not any(t.casefold() in texto_min for t in esperado["contem_algum"]):
        falhas.append("não citou nenhuma das linhas esperadas")
    for trecho in esperado.get("nao_contem", []):
        if trecho.casefold() in texto_min:
            falhas.append(f"citou '{trecho}'")
    if "acao_linha" in esperado:
        if esperado["acao_linha"] is None and acao:
            falhas.append("criou ação sem poder")
        elif esperado["acao_linha"] and esperado["acao_linha"] not in linhas_acao:
            falhas.append(f"ação esperada: esperar {esperado['acao_linha']}")
    for linha in esperado.get("acao_nao", []):
        if linha in linhas_acao:
            falhas.append(f"ação indevida: {linha}")
    return falhas


def main() -> None:
    argumentos = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    argumentos.add_argument("--api", default="https://sonar.rodrigoviana.app.br/api")
    argumentos.add_argument("--com-olhovivo", action="store_true")
    argumentos.add_argument("--intervalo", type=float, default=5.0, help="segundos entre perguntas")
    opcoes = argumentos.parse_args()

    perguntas = json.loads((PASTA / "perguntas.json").read_text(encoding="utf-8"))
    if not opcoes.com_olhovivo:
        perguntas = [p for p in perguntas if not p.get("requer_olhovivo")]

    resultados = []
    with httpx.Client(base_url=opcoes.api.rstrip("/"), timeout=40) as cliente:
        for i, pergunta in enumerate(perguntas):
            if i:
                time.sleep(opcoes.intervalo)
            inicio = time.perf_counter()
            try:
                resposta = cliente.post("/ia/perguntar", json={"texto": pergunta["texto"], "parada_id": pergunta["parada_id"]})
                resposta.raise_for_status()
                corpo = resposta.json()
            except httpx.HTTPError as erro:
                corpo = {"status": "erro", "resposta_falada": f"{erro.__class__.__name__}: {erro}"}
            segundos = round(time.perf_counter() - inicio, 2)
            falhas = conferir(pergunta["esperado"], corpo)
            llm = any(str(f).startswith("llm:") for f in corpo.get("fontes", []))
            resultados.append({**pergunta, "resposta": corpo, "segundos": segundos, "falhas": falhas, "llm": llm})
            marca = "OK  " if not falhas else "ERRO"
            print(f"{marca} {segundos:5.1f}s {'LLM ' if llm else 'regr'} {pergunta['id']}: {corpo.get('resposta_falada', '')[:90]}")
            if falhas:
                print(f"           {'; '.join(falhas)}")

    acertos = sum(1 for r in resultados if not r["falhas"])
    tempos = [r["segundos"] for r in resultados]
    p95 = sorted(tempos)[max(0, round(0.95 * len(tempos)) - 1)]
    resumo = (
        f"**{acertos} de {len(resultados)} certas ({100 * acertos / len(resultados):.0f}%)**; "
        f"latência mediana {statistics.median(tempos):.1f} s, p95 {p95:.1f} s; "
        f"{sum(r['llm'] for r in resultados)} respondidas pelo LLM e "
        f"{sum(not r['llm'] for r in resultados)} pelas regras (fallback ou sem LLM)."
    )
    linhas = [
        "# Avaliação do agente de IA do Sonar",
        "",
        f"API: `{opcoes.api}` · {time.strftime('%d/%m/%Y %H:%M')}",
        "",
        resumo,
        "",
        "| # | Pergunta | Resposta | Quem respondeu | Tempo | Resultado |",
        "|---|---|---|---|---|---|",
    ]
    for n, r in enumerate(resultados, 1):
        resposta = r["resposta"].get("resposta_falada", "").replace("|", "/")
        resultado = "acertou" if not r["falhas"] else "errou: " + "; ".join(r["falhas"])
        quem = "LLM" if r["llm"] else "regras"
        linhas.append(f"| {n} | {r['texto']} | {resposta} | {quem} | {r['segundos']} s | {resultado} |")
    (PASTA / "resultado.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    (PASTA / "resultado.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + resumo)
    print(f"Tabela para o relatório: {PASTA / 'resultado.md'}")


if __name__ == "__main__":
    main()
