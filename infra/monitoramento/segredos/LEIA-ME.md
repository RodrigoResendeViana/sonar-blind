Arquivos desta pasta ficam fora do Git (veja o .gitignore). Crie:

- `metricas_senha`: a senha do Prometheus, do Parameter Store (`/sonar/metricas/senha`)
- `telegram_token`: o token do bot criado no @BotFather
- `grafana_senha`: a senha do usuário admin do Grafana (invente uma)

Cada arquivo tem só o valor, sem quebra de linha no fim (`printf '%s' "valor" > arquivo`).
