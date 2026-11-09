# Robô de RPA (equipe de RPA)

Quando o ônibus passa direto e o passageiro consente, a API cria uma ocorrência. O robô:

1. lê as pendentes em `GET /api/ocorrencias?status=pendente` (a cada 15 min);
2. confere os dados (linha, horário, leitura da câmera, aviso ao motorista);
3. registra a reclamação no canal da SPTrans (156 / portal) e pega o protocolo;
4. devolve `PATCH /api/ocorrencias/{id}` com `enviada` + protocolo (ou `inconclusiva`,
   `duplicada`, `erro`). O app fala o protocolo para o passageiro.

Contrato completo em [`docs/contratos.md`](../docs/contratos.md#ocorrências-api--robô-de-rpa).
Autenticação: `Authorization: Bearer <token>`, do Parameter Store `/sonar/api/token-servico`.

Este esqueleto já faz os passos 1, 2 e 4. A equipe implementa `registrar()` em
`sonar_rpa/portal.py` (UiPath, Playwright ou o que a matéria pedir). Se a ferramenta for
UiPath, deixe o projeto em `rpa/uipath/` e mantenha este cliente como referência do contrato.

## Rodar e testar

```bash
cd rpa
pip install -r requirements-dev.txt
pytest
SONAR_API_URL=http://localhost/api SONAR_TOKEN=... python -m sonar_rpa --uma-vez
```

Nunca registre reclamação real a partir dos dados de demonstração: use `--simular`.
