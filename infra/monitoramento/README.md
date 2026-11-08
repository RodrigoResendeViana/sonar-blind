# Monitoramento (servidor local)

Prometheus, Alertmanager, Grafana e blackbox exporter rodando no seu servidor. Eles só fazem
**conexões de saída** (buscam as métricas na EC2 por HTTPS, com senha, e mandam alertas ao
Telegram), então o servidor não precisa de IP público nem de porta aberta no roteador.

| O quê | Onde |
|---|---|
| Métricas da API (tráfego, erros, latência, Olho Vivo, dispositivos) | `https://sonar.rodrigoviana.app.br/metrics` |
| Métricas da EC2 (CPU, memória, disco) | `https://sonar.rodrigoviana.app.br/node-metrics` |
| Teste de fora (site no ar, validade do certificado) | blackbox exporter |
| Painel | Grafana em `http://<ip-do-servidor>:3000` (usuário `admin`) |

## Subir

Precisa de Docker com o plugin Compose (no Linux: `sudo apt install docker.io docker-compose-v2`, ou o Docker Desktop).

1. **Bot do Telegram.** No Telegram, fale com o `@BotFather`, mande `/newbot` e guarde o token. Mande
   qualquer mensagem para o seu bot e abra `https://api.telegram.org/bot<TOKEN>/getUpdates`: o número
   em `"chat":{"id": ...}` é o seu chat_id.
2. **Segredos** (ficam fora do Git):
   ```bash
   cd infra/monitoramento
   printf '%s' "$(aws ssm get-parameter --name /sonar/metricas/senha --with-decryption --query Parameter.Value --output text)" > segredos/metricas_senha
   printf '%s' "TOKEN-DO-BOT" > segredos/telegram_token
   printf '%s' "uma-senha-para-o-grafana" > segredos/grafana_senha
   cp .env.example .env   # e preencha TELEGRAM_CHAT_ID
   ```
   O comando `aws` roda no CloudShell; se o seu servidor não tiver o AWS CLI, copie a senha de lá.
3. `docker compose up -d` e abra o Grafana. O painel "Sonar — sinais de ouro" já vem pronto.

Prometheus (`:9090`) e Alertmanager (`:9093`) ficam só em `127.0.0.1`. Para vê-los de outra
máquina da rede: `ssh -L 9090:localhost:9090 usuario@servidor`.

## Alertas (Telegram)

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

**Disparar um alerta para o print:** desligue o Sonar Ponto da tomada e espere 5 min (alerta
"Sonar Ponto offline"). Ou, pelo SSM, pare a API por 3 min:
`aws ssm start-session --target <id-da-instancia>` e `sudo docker compose -f /opt/sonar/repo/infra/compose/docker-compose.yml stop api`
(depois, `start api`).
