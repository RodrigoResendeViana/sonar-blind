# Execução barrada e corrigida (para o PDF)

O critério pede uma execução do pipeline barrada por um problema de segurança e a correção.

## A que aconteceu de verdade (08/11/2026)

| | Execução | Commit | Resultado |
|---|---|---|---|
| Barrada | [run 42534024438](https://github.com/RodrigoResendeViana/sonar-blind/actions/runs/42534024438) | `00d0272` | Trivy barrou as imagens `api` e `web` |
| Correção | [`3fd80c6`](https://github.com/RodrigoResendeViana/sonar-blind/commit/3fd80c6) e [`f49ca4a`](https://github.com/RodrigoResendeViana/sonar-blind/commit/f49ca4a) | | ver abaixo |
| Corrigida | [run 42535631976](https://github.com/RodrigoResendeViana/sonar-blind/actions/runs/42535631976) | `8c4453d` | todos os jobs verdes |

- **Imagem `api`**: 5 CVEs altas em `urllib3`, `msgpack` e `setuptools`, que não eram do Sonar: vinham
  dentro do próprio `pip` da imagem (e mais o `zlib` do Debian). Correção (`3fd80c6`): o `pip` sai da
  imagem final e a imagem aplica as correções de segurança do Debian (`apt-get upgrade`).
- **Imagem `web`**: CVE no `golang.org/x/net` compilado dentro do binário do Caddy, sem versão
  corrigida publicada na época. Correção (`f49ca4a`): exceção justificada no `.trivyignore` (o
  Caddyfile do Sonar não usa templates nem processa HTML), com a condição para remover.

Prints: o job vermelho com a tabela de CVEs, o diff do `3fd80c6` e o resumo verde da execução
corrigida.

## Para repetir na frente do professor (opcional)

O roteiro abaixo usa uma imagem base antiga: o Trivy encontra CVEs altas e críticas que já têm
correção e barra o job antes de qualquer imagem chegar ao GHCR.

1. Crie a branch: `git checkout -b demo/imagem-antiga`.
2. Em `api/Dockerfile`, troque as **duas** linhas `FROM python:3.13-slim` por
   `FROM python:3.11.0-slim` (imagem de outubro de 2022).
3. `git commit -am "demo: imagem base antiga" && git push -u origin demo/imagem-antiga` e abra um
   pull request para a `main`.
4. No Actions, o job "Imagem api" fica vermelho no passo "Trivy (barra CVE alta ou crítica que já
   tem correção)". **Print 1:** o job vermelho e a tabela de CVEs do log.
5. Corrija: volte as duas linhas para `python:3.13-slim`, commit e push na mesma branch.
6. O pipeline fica verde. **Print 2:** a execução verde no mesmo pull request.
7. Feche o pull request sem fazer merge (ou faça merge só da correção).

Outra opção: o Gitleaks. Num commit, crie `api/.env` com `OLHOVIVO_TOKEN=` seguido de 64
caracteres hexadecimais aleatórios (`openssl rand -hex 32`, nunca o token verdadeiro) e force o
`git add -f`. O job "Segredos (Gitleaks)" barra o push. A correção é apagar o arquivo e reescrever
o commit (`git reset HEAD~1`), porque o segredo ficaria no histórico.
