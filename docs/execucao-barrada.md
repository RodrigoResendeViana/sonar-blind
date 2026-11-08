# Execução barrada e corrigida (para o PDF)

O critério pede uma execução do pipeline barrada por um problema de segurança e a correção.
O roteiro usa uma imagem base antiga: o Trivy encontra CVEs altas e críticas que já têm
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
