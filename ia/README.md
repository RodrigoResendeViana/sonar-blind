# Agente de IA generativa (equipe de GenAI)

Responde às perguntas por voz do passageiro. A API chama `POST {SONAR_IA_URL}/perguntar`
com o contrato de [`docs/contratos.md`](../docs/contratos.md#pergunta-por-voz-app--api--ia)
e valida a resposta; fora do esquema ou acima de 20 s vira `nao_consta`.

Este esqueleto já cumpre o contrato com um responder simples. A equipe troca o
`responder()` em `sonar_ia/agente.py` pelo agente de verdade (LLM + RAG sobre o cadastro das
paradas e a previsão do Olho Vivo), sem mudar a rota.

## Regras do agente

- Responde só com o que vem das fontes (cadastro e previsão). Sem fonte: `status: "nao_consta"`.
- `resposta_falada` curta (até 600 caracteres), pensada para leitor de tela.
- Preencher `fontes` e uma `confianca` honesta (0 a 1).
- Não guarda a pergunta nem dado pessoal.

## Rodar e testar

```bash
cd ia
pip install -r requirements-dev.txt
pytest
uvicorn sonar_ia.main:app --port 8100
```

Para ligar na API local: `SONAR_IA_URL=http://localhost:8100` no `.env` do compose.
Com o perfil `ia` do compose, o Ollama fica em `http://ollama:11434` para o modelo local.
