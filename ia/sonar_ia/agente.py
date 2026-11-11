"""Agente de IA generativa do Sonar: entende a pergunta e consulta os dados reais por ferramentas.

O LLM (Ollama) nunca responde de memória sobre ônibus: ele chama as ferramentas, que leem a API do
Sonar (que por sua vez lê o Olho Vivo da SPTrans). Se nenhuma ferramenta trouxe dado, a resposta é
"nao_consta", não importa o que o modelo escreveu.
"""

import json
import re
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from .ferramentas import DEFINICOES, Ferramentas

MAX_RODADAS = 4

INSTRUCOES = """Você é o Sonar, assistente de voz para pessoas cegas que esperam ônibus em São Paulo.
Regras:
- Use SEMPRE as ferramentas para saber linhas, destinos e horários. Nunca invente número de linha,
  destino ou tempo de chegada.
- Se o passageiro disser um destino ("quero ir para a Lapa"), use buscar_linha com o nome do lugar.
- Se houver parada_id, use previsao_parada para dizer em quantos minutos a linha chega.
- Se as ferramentas não trouxerem a informação, diga que não consta.
- Responda em português, em no máximo duas frases curtas, sem listas, sem emojis e sem markdown:
  o texto vai ser lido por um leitor de tela.
- Fale o código da linha como aparece nos dados (ex.: 8000-10)."""


class Pergunta(BaseModel):
    texto: str = Field(min_length=1, max_length=500)
    parada_id: str | None = Field(default=None, max_length=64)


class Resposta(BaseModel):
    status: Literal["ok", "nao_consta"]
    resposta_falada: str = Field(max_length=600)
    acao: dict | None = None
    fontes: list[str] = Field(default_factory=list)
    confianca: float = Field(default=0.0, ge=0.0, le=1.0)


NAO_CONSEGUI = Resposta(status="nao_consta", resposta_falada="Não consegui responder agora. Tente de novo em instantes.")


def _limpar(texto: str) -> str:
    texto = re.sub(r"[*_#`>]", "", texto or "")
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto[:600]


class Agente:
    def __init__(self, ollama: httpx.AsyncClient, ferramentas: Ferramentas, modelo: str):
        self.ollama = ollama
        self.ferramentas = ferramentas
        self.modelo = modelo

    async def _chat(self, mensagens: list[dict]) -> dict:
        resposta = await self.ollama.post(
            "/api/chat",
            json={
                "model": self.modelo,
                "messages": mensagens,
                "tools": DEFINICOES,
                "stream": False,
                "options": {"temperature": 0.1},
            },
        )
        resposta.raise_for_status()
        return resposta.json()["message"]

    async def responder(self, pergunta: Pergunta) -> Resposta:
        contexto = f"Pergunta do passageiro: {pergunta.texto}"
        if pergunta.parada_id:
            contexto += f"\nO passageiro está na parada_id={pergunta.parada_id}."
        mensagens = [{"role": "system", "content": INSTRUCOES}, {"role": "user", "content": contexto}]
        fontes: list[str] = []
        linhas_vistas: set[str] = set()
        try:
            for _ in range(MAX_RODADAS):
                mensagem = await self._chat(mensagens)
                chamadas = mensagem.get("tool_calls") or []
                if not chamadas:
                    break
                mensagens.append(mensagem)
                for chamada in chamadas:
                    funcao = chamada.get("function", {})
                    resultado = await self.ferramentas.executar(funcao.get("name", ""), funcao.get("arguments") or {})
                    if resultado.get("fonte"):
                        fontes.append(resultado["fonte"])
                    linhas_vistas.update(resultado.get("codigos", []))
                    mensagens.append({"role": "tool", "content": json.dumps(resultado, ensure_ascii=False)})
            else:
                mensagem = await self._chat(mensagens + [{"role": "user", "content": "Responda agora, sem ferramentas."}])
        except (httpx.HTTPError, KeyError, ValueError):
            return NAO_CONSEGUI

        texto = _limpar(mensagem.get("content", ""))
        if not fontes or not texto:
            # sem dado de ferramenta, nada do que o modelo disse pode ir para o passageiro
            return Resposta(
                status="nao_consta",
                resposta_falada="Não consta essa informação. Diga o número da linha ou para onde você quer ir.",
            )
        citadas = sorted(codigo for codigo in linhas_vistas if codigo.upper() in texto.upper())
        acao = None
        if pergunta.parada_id and citadas:
            acao = {"tipo": "esperar", "parada_id": pergunta.parada_id, "linhas": citadas[:1]}
        return Resposta(
            status="ok",
            resposta_falada=texto,
            acao=acao,
            fontes=sorted(set(fontes)),
            confianca=0.8 if citadas else 0.6,
        )
