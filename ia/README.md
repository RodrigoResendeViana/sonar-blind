# Agente de IA generativa (equipe de GenAI)

Entende a pergunta do passageiro (texto vindo da voz) e responde com dados reais. A API do Sonar
chama `POST {SONAR_IA_URL}/perguntar` com o contrato de
[`docs/contratos.md`](../docs/contratos.md#pergunta-por-voz-app--api--ia) e valida a resposta.

```
voz (Web Speech API no app) → texto → API /ia/perguntar → agente → Ollama (LLM local)
                                                              ↘ ferramentas → API /linhas e /paradas/{id}/previsao → Olho Vivo
```

## Como funciona

- **LLM local** no Ollama (padrão `qwen2.5:3b`, que suporta *tool calling*), na própria EC2:
  nenhuma pergunta sai para um serviço de terceiros.
- **Ferramentas** (`sonar_ia/ferramentas.py`), só de leitura, sempre pela API do Sonar:
  - `buscar_linha(termo)`: linha por número ou destino ("Lapa" → 8000-10, sentido Terminal Lapa);
  - `previsao_parada(parada_id)`: próximos ônibus e minutos até chegar.
- **Guarda-corpos** (`sonar_ia/agente.py`):
  - se nenhuma ferramenta trouxe dado, a resposta vira `nao_consta`, mesmo que o modelo tenha
    escrito algo (o modelo não fala de memória);
  - argumentos das ferramentas validados por regex (nada de `../` nem texto livre na URL);
  - no máximo 4 rodadas de ferramenta; resposta limpa de markdown e cortada em 600 caracteres
    (vai para o leitor de tela);
  - `acao: esperar` só sai quando a linha citada veio de uma ferramenta e há `parada_id`.

## Rodar e testar

```bash
cd ia
pip install -r requirements-dev.txt
pytest                                   # o LLM e a API são simulados nos testes
```

Com o compose local (precisa de ~4 GB livres para o modelo):

```bash
cd infra/compose
COMPOSE_PROFILES=ia SONAR_IA_URL=http://ia:8100 docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
docker compose exec ollama ollama pull qwen2.5:3b
curl -s localhost/api/ia/perguntar -H 'content-type: application/json' \
  -d '{"texto":"quando chega a DEMO-10?","parada_id":"demo"}'
```

## Na AWS

Parâmetros no Parameter Store (CloudShell):

```bash
aws ssm put-parameter --name /sonar/compose/perfis --type String --value ia --overwrite
aws ssm put-parameter --name /sonar/ia/url --type String --value http://ia:8100 --overwrite
aws ssm put-parameter --name /sonar/ia/modelo --type String --value qwen2.5:3b --overwrite
```

O próximo deploy sobe o Ollama e o agente e baixa o modelo.

## Para a entrega de GenAI

- Avaliação: um conjunto de 15 a 20 perguntas (linha certa, destino, linha que não passa no
  ponto, pergunta fora do assunto) com a resposta esperada; medir acerto e latência
  (a métrica `sonar_ia_latencia_segundos` já está no Grafana).
- Mostrar o caso em que o modelo "inventa" e o guarda-corpo transforma em `nao_consta`.
