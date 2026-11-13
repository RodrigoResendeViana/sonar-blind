# Sonar — Secure DevOps

**FIAP · Global Solution 2026.2 · CitizenTech**
Grupo: [PREENCHER] · Integrantes (RM): [PREENCHER]
Repositório: https://github.com/RodrigoResendeViana/sonar-blind · Site: https://sonar.rodrigoviana.app.br

## 1. Visão geral

O Sonar (app de voz, API, IA, RPA e dispositivos IoT) roda numa EC2 na AWS criada por Terraform e é
publicado por um pipeline do GitHub Actions que barra segredos, código vulnerável e imagens com CVE
antes de qualquer deploy. Arquitetura: `docs/arquitetura.md`.

[PRINT: diagrama de arquitetura]

## 2. Infraestrutura como código

- `infra/terraform/bootstrap`: bucket S3 do estado (versionado, cifrado, sem acesso público).
- `infra/terraform/nuvem`: VPC/SG (só 80, 443 e 8883), EC2 com IMDSv2 (hop limit 1) e disco cifrado,
  papéis IAM mínimos, provedor OIDC do GitHub (confiança só na branch `main` deste repositório, com o
  `sub` no formato com IDs imutáveis), Parameter Store para todos os segredos, AWS Budgets.
- Estado e `terraform.tfvars` fora do repositório; o pipeline nunca roda o Terraform.

[PRINT: `terraform plan` sem mudanças] [PRINT: Parameter Store com os parâmetros /sonar/*]

## 3. Pipeline

| Etapa | Ferramenta | Barra o quê |
|---|---|---|
| Segredos | Gitleaks | chave/token no histórico |
| SAST | Semgrep | código inseguro, ações sem SHA fixo |
| Testes | pytest (API, IA, câmera, RPA, visão), Vitest + axe (acessibilidade), PlatformIO | regressão |
| IaC | Terraform fmt/validate + Trivy config | configuração insegura na nuvem |
| Imagens | Trivy (CVE altas/críticas com correção) + SBOM | imagem vulnerável chegando ao GHCR |
| Deploy | OIDC (sem chave da AWS guardada) + `ssm send-command` (sem SSH) | — |

[PRINT: pipeline verde com todos os jobs] [PRINT: a execução barrada pelo Trivy e a correção —
roteiro em `docs/execucao-barrada.md`]

## 4. Segurança em execução

- Containers sem root, `cap_drop: ALL`, `no-new-privileges`, sistema de arquivos só leitura, limite de
  memória (`infra/compose/docker-compose.yml`).
- HTTPS automático (Caddy + Let's Encrypt), HSTS, CSP restritiva; MQTT com TLS, senha e ACL por
  dispositivo; n8n e métricas só na rede interna.
- LGPD: mapa de dados em `docs/lgpd.md` (consentimento, minimização, sem imagem saindo do ponto, LLM
  local). Responsabilidade compartilhada: `docs/responsabilidade-compartilhada.md`.

## 5. Monitoramento

Prometheus, Alertmanager (Telegram) e Grafana em `/grafana`, na própria EC2, lendo pela rede interna.
Alertas: API fora, p95 alto, IA lenta ou caindo para as regras, memória da EC2, certificado perto de
vencer, entre outros (`infra/monitoramento/prometheus/alertas.yml`).

[PRINT: painel do Grafana] [PRINT: um alerta chegando no Telegram]

## 6. Custo

`docs/custo.md`: [PREENCHER: custo estimado e o gasto real no período].

## 7. Problemas reais resolvidos

| Problema | Causa | Correção |
|---|---|---|
| Deploy negado pelo STS (`AssumeRoleWithWebIdentity`) | o GitHub mandava o `sub` com IDs imutáveis do dono e do repositório | trust policy aceita os dois formatos, sempre só a `main` |
| Alertmanager não subia | segredo montado dentro de uma pasta já montada como só leitura | segredo em `/run/segredos` |
| Certificado não saiu de primeira | o registro DNS do subdomínio ainda não existia (NXDOMAIN) | registro A do `sonar` e nova tentativa automática do Caddy |
| [PREENCHER] | | |
