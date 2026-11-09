# Como contribuir

## Quem cuida de quê

| Matéria | Pasta | Contrato |
|---|---|---|
| IA generativa | `ia/` | `POST /perguntar` em `docs/contratos.md` |
| Visão computacional | `visao/` e `edge/` | leitura publicada em `sonar/parada/{id}/visao` |
| RPA | `rpa/` | `GET/PATCH /api/ocorrencias` |
| Maker Lab | `firmware/` | tópicos MQTT em `docs/contratos.md` |
| Secure DevOps | `infra/`, `.github/` | pipeline e deploy |
| App e API | `app/`, `api/` | `docs/openapi.json` |

Mudou um contrato? Atualize `docs/contratos.md` no mesmo PR e avise as outras equipes.

## Fluxo

1. `git clone https://github.com/RodrigoResendeViana/sonar-blind.git` e `git checkout main && git pull`
2. Crie um branch: `git checkout -b feat/ia-rag` (prefixos: `feat/`, `fix/`, `docs/`, `ci/`)
3. Commits pequenos, em português, no padrão `tipo(pasta): o que mudou`
   — ex.: `feat(ia): responde a previsão a partir do Olho Vivo`
4. Rode os testes da sua pasta antes do push (abaixo).
5. `git push -u origin feat/ia-rag` e abra o PR para `main`.
6. O pipeline precisa ficar verde e o Rodrigo revisa e faz o merge. O merge na `main` faz o deploy.

## Testar

| Pasta | Comando |
|---|---|
| `api/` | `pip install -r requirements-dev.txt && pytest` |
| `ia/` | `pip install -r requirements-dev.txt && pytest` (servidor: `uvicorn sonar_ia.main:app --port 8100`) |
| `rpa/` | `pip install -r requirements-dev.txt && pytest` |
| `edge/` | `pip install -r requirements-dev.txt && pytest` |
| `app/` | `npm ci && npm test` |
| `firmware/` | `pio run` ou a simulação no Wokwi |
| tudo junto | `cd infra/compose && docker compose -f docker-compose.yml -f docker-compose.local.yml up --build` → http://localhost |

Sem token do Olho Vivo, o sistema roda em modo demonstração (`POST /api/demo/esperas`).

## Regras

- **Nenhum segredo no Git** (token, senha, chave). O Gitleaks barra o PR. Segredo vai no
  Parameter Store `/sonar/*`; para rodar local, use o `.env` (que está no `.gitignore`).
- Nada de dado pessoal real em teste ou dataset (LGPD, veja `docs/lgpd.md`).
- Dependência nova: versão fixa no `requirements.txt` / `package-lock.json`.
