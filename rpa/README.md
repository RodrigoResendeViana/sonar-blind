# Robô de RPA (equipe de RPA)

Quando o ônibus passa direto e o passageiro consente, a API cria uma **ocorrência** com as
evidências do ponto (leitura da câmera, tempo parado, aviso ao motorista e o "ciente" dele).
O robô transforma isso em reclamação formal, sem o passageiro precisar ligar no 156.

A automação principal é um fluxo do **n8n** (`n8n/ocorrencias.json`):

```
a cada 15 min ─▶ GET /ocorrencias?status=pendente ─▶ conferir evidências ─▶ registrar no canal oficial ─▶ PATCH /ocorrencias/{id}
                                                     (consentimento, linha,     (MVP: simulado, gera        (enviada + protocolo, ou
                                                      câmera ou ciente)          protocolo SIM-...)          inconclusiva + motivo)
```

O app fala o protocolo para o passageiro assim que a API recebe o `PATCH`.
Contrato: [`docs/contratos.md`](../docs/contratos.md#ocorrências-api--robô-de-rpa).

## Segurança

- O n8n **não fica exposto na internet**: escuta só em `127.0.0.1:5678` da EC2. Para abrir o
  editor, use um túnel do SSM (comando em `terraform output abrir_o_n8n`) e acesse
  http://localhost:5678.
- O token da API (`/sonar/api/token-servico`) e a chave que cifra as credenciais do n8n
  (`/sonar/n8n/chave`) vêm do Parameter Store pelo deploy; nada disso fica no fluxo exportado.
- Credenciais extras (bot do Telegram, e-mail) são cadastradas na tela do n8n e ficam cifradas
  no volume dele, não no Git.

## Ligar na AWS

```bash
# CloudShell: adicione "rpa" aos perfis (junto com "ia", se já estiver usando)
aws ssm put-parameter --name /sonar/compose/perfis --type String --value ia,rpa --overwrite
```

O próximo deploy sobe o n8n e importa os fluxos de `rpa/n8n/`. Depois, no seu computador (precisa
do AWS CLI e do [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)):

```bash
aws ssm start-session --target <id-da-ec2> --document-name AWS-StartPortForwardingSession \
  --parameters portNumber=5678,localPortNumber=5678
```

Abra http://localhost:5678, crie o usuário dono, abra o fluxo "Sonar - ocorrências..." e ative-o.

## Testar ponta a ponta

1. No app, rode a demonstração "não parou" (`POST /api/demo/esperas` com `{"cenario":"nao_parou"}`)
   e aceite registrar a reclamação.
2. No n8n, clique em **Rodar agora (demo)**.
3. O app fala "Sua reclamação foi registrada com o protocolo SIM-...".

## O que a equipe de RPA evolui

- Trocar o registro simulado por um canal real: nó **Send Email** para a ouvidoria da SPTrans
  ou **HTTP Request** para o formulário do SP156, guardando o protocolo devolvido.
- Nó do **Telegram** avisando a equipe de cada reclamação enviada.
- Nó do **Google Sheets** com o histórico (base para Big Data depois).
- Tratamento de erro: um fluxo de erro do n8n que marca a ocorrência como `erro`.

## Cliente em Python (referência)

`sonar_rpa/` faz o mesmo ciclo em Python e tem testes do contrato (`pytest`). Serve para testar a
API sem o n8n e como referência para quem preferir outra ferramenta de RPA.
