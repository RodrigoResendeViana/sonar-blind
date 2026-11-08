# Sonar

**Pegar o ônibus certo sem depender de um desconhecido.** O Sonar resolve os últimos 20 metros
da viagem de ônibus de uma pessoa cega: saber qual ônibus parou na frente dela e garantir que o
motorista saiba que ela está ali.

- **App de voz (PWA):** a pessoa pergunta pela linha, chega ao ponto e ouve "chegando agora:
  linha 8000-10. É o seu", com vibração longa.
- **Sonar Ponto:** ESP32 com ultrassom, LED e buzzer, mais uma câmera que lê o letreiro. Apita
  para a pessoa achar o poste, pisca o LED para o motorista e registra cada passagem.
- **Sonar Bordo:** o bipper na cabine. Avisa o motorista duas paradas antes; ele confirma com um
  toque e a pessoa ouve "o motorista confirmou".
- **Prova quando o ônibus não para:** com o "sim" do usuário, um robô registra a reclamação com
  as evidências do ponto e devolve o protocolo.

Projeto da Global Solution 2026.2 (CitizenTech), 4º ano de Engenharia de Software da FIAP.

## Ficha técnica

| Integrante | RM | Frente |
|---|---|---|
| Rodrigo Viana | _preencher_ | Secure DevOps, Maker Lab |
| _preencher_ | _preencher_ | _preencher_ |
| _preencher_ | _preencher_ | _preencher_ |
| _preencher_ | _preencher_ | _preencher_ |
| _preencher_ | _preencher_ | _preencher_ |

| Link | |
|---|---|
| App no ar | https://sonar.rodrigoviana.app.br |
| API (OpenAPI) | https://sonar.rodrigoviana.app.br/api/docs |
| Vídeo do Maker Lab | _preencher_ |
| Vídeo de apresentação | _preencher_ |

## Experimente

Abra o app e toque em **Ver a jornada completa**: em cerca de 2 minutos ele roda a espera, o
aviso ao motorista, um ônibus errado, o certo e o embarque, com dados de exemplo. Abra ao mesmo
tempo, em outra aba, a tela **Motorista (simulado)** para apertar o "Ciente", ou **Ponto
(simulado)** para fazer o papel da câmera.

## Repositório

```
sonar/
├── app/                    PWA (React + Vite + TypeScript), servido pelo Caddy
├── api/                    API (FastAPI): esperas, SSE, MQTT, Olho Vivo, IA, ocorrências, métricas
├── edge/                   serviço da câmera do ponto (YOLO + OCR; só publica texto)
├── firmware/               Sonar Ponto e Sonar Bordo (PlatformIO + Wokwi)
├── infra/terraform/        bootstrap (bucket do state) e nuvem (VPC, EC2, IAM, OIDC, SSM, Budgets)
├── infra/compose/          docker-compose, Caddyfile, Mosquitto e o deploy.sh
├── infra/monitoramento/    Prometheus, alertas no Telegram e Grafana (rodam na EC2)
├── .github/workflows/      ci-cd.yml: Gitleaks, Semgrep, testes, Trivy, GHCR, deploy por SSM, ZAP
└── docs/                   contratos, arquitetura, LGPD, custo, responsabilidade compartilhada
```

## Rodar na sua máquina

Precisa de Docker com Compose.

```bash
cd infra/compose
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

Abra http://localhost. Sem o token do Olho Vivo, o app funciona no modo demonstração.

Desenvolvimento: `cd api && pip install -r requirements-dev.txt && pytest`;
`cd app && npm ci && npm test && npm run dev` (a API em `localhost:8000`, via
`uvicorn --factory sonar_api.main:create_app`).

## Segurança e DevOps

- **Pipeline** (`.github/workflows/ci-cd.yml`): a cada push, Gitleaks nos commits novos, Semgrep
  (padrão e OWASP Top 10), testes da API, do app (com checagem de acessibilidade pelo axe), da
  câmera e compilação do firmware, `terraform validate` e Trivy na configuração, nas dependências
  e nas imagens, com SBOM. Na `main`: imagens no GHCR, deploy pelo AWS SSM e teste de fumaça em
  `/healthz`, mais um ZAP baseline.
- **Sem segredo no Git:** o deploy gera o `.env` a partir do Parameter Store; o pipeline entra na
  AWS por OIDC, sem chave guardada; a EC2 não tem porta 22.
- **Observabilidade:** a API expõe `/metrics` (tráfego, erros, latência, Olho Vivo, dispositivos);
  o Grafana em `/grafana` mostra os sinais de ouro, e os alertas vão para o Telegram.
- Detalhes: [arquitetura](docs/arquitetura.md), [contratos](docs/contratos.md),
  [LGPD](docs/lgpd.md), [custo](docs/custo.md),
  [responsabilidade compartilhada](docs/responsabilidade-compartilhada.md) e
  [primeira subida](docs/bootstrap.md).
