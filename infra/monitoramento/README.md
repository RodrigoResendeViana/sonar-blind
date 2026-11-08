# Monitoramento (na EC2)

Prometheus, Alertmanager, blackbox exporter e Grafana sobem junto com o Sonar, no mesmo
`docker compose` da EC2 (perfil `producao`). Nada roda no servidor local.

| O quê | Onde |
|---|---|
| Métricas da API (tráfego, erros, latência, Olho Vivo, dispositivos) | Prometheus lê `api:8000/metrics` pela rede interna |
| Métricas da EC2 (CPU, memória, disco) | `node-exporter:9100`, também pela rede interna |
| Teste de fora (site no ar, validade do certificado) | blackbox exporter acessando o domínio pela internet |
| Painel | **https://sonar.rodrigoviana.app.br/grafana** (usuário `admin`) |

Nenhuma dessas portas fica aberta para a internet: só o Grafana, atrás do Caddy, com login.

## Senha do Grafana

Gerada pelo Terraform. No CloudShell:

```bash
aws ssm get-parameter --name /sonar/grafana/senha --with-decryption --query Parameter.Value --output text
```

## Alertas no Telegram

1. No Telegram, fale com o `@BotFather`, mande `/newbot` e guarde o token.
2. Mande qualquer mensagem para o bot e abra `https://api.telegram.org/bot<TOKEN>/getUpdates`; o
   número em `"chat":{"id": ...}` é o chat_id.
3. Grave os dois no Parameter Store (CloudShell) e rode o deploy de novo (Actions > ci-cd > Run workflow):

```bash
read -rsp "Token do bot: " T && echo
aws ssm put-parameter --name /sonar/telegram/token --type SecureString --value "$T" --overwrite && unset T
aws ssm put-parameter --name /sonar/telegram/chat-id --type String --value "SEU_CHAT_ID" --overwrite
```

Sem esses parâmetros, o Alertmanager sobe e os alertas aparecem só no Grafana/Prometheus.

| Alerta | Quando |
|---|---|
| SonarApiForaDoAr | o Prometheus não lê `/metrics` há 2 min |
| SiteIndisponivel | o site não responde de fora há 2 min |
| OlhoVivoIndisponivel | o Olho Vivo falha há 5 min |
| SonarPontoOffline | um Sonar Ponto está sem sinal de vida há 5 min |
| ErrosAcimaDe5PorCento | mais de 5% de respostas 5xx em 5 min |
| LatenciaAlta, IALenta | p95 da API acima de 1 s; IA acima de 8 s |
| MemoriaDaEC2, DiscoDaEC2 | memória abaixo de 10%; disco abaixo de 15% |
| CertificadoVencendo | o HTTPS vence em menos de 14 dias |

**Disparar um alerta para o print:** desligue o Sonar Ponto e espere 5 min ("Sonar Ponto offline").
Observação: se a própria EC2 cair, o monitoramento cai junto; o teste de fumaça do pipeline e o
AWS Budgets continuam de fora.
