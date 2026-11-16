# Robô de RPA

Quando o ônibus passa direto e o passageiro consente, a API cria uma **ocorrência** com as
evidências do ponto (leitura da câmera, tempo parado, aviso ao motorista e o "ciente" dele).
O robô transforma isso em reclamação formal, sem o passageiro precisar ligar no 156.

A automação principal é um fluxo do **n8n** (`n8n/ocorrencias.json`):

```
aviso da API (webhook, na hora) ─┐
a cada 15 min (rede de segurança) ┼─▶ GET /ocorrencias?status=pendente ─▶ conferir evidências ─▶ registrar no canal ─▶ PATCH /ocorrencias/{id}
"Rodar agora" (demo, no editor) ──┘                                        (consentimento, linha,  (MVP: simulado,       (enviada + protocolo, ou
                                                                            câmera ou ciente)       protocolo SIM-...)     inconclusiva + motivo)
```

Assim que o passageiro aceita registrar a reclamação, a API chama o webhook interno do n8n
(`http://n8n:5678/webhook/sonar-ocorrencia`, só na rede do compose) e o passageiro ouve o protocolo
em segundos. Se o aviso falhar, o agendamento de 15 minutos pega a ocorrência depois: nada se perde.
Contrato: [`docs/contratos.md`](../docs/contratos.md#ocorrências-api--robô-de-rpa).

## Já vem ligado

O deploy sobe o n8n (perfil `rpa`, ligado por padrão), **importa e publica** o fluxo deste repositório
e reinicia o n8n. Não é preciso abrir o editor para o RPA funcionar.

O repositório é a fonte da verdade: cada deploy reimporta `rpa/n8n/*.json`, então uma mudança
feita só no editor é desfeita no deploy seguinte. Para mudar o fluxo, exporte do editor (menu ⋯ →
*Download*) e salve em `rpa/n8n/`.

## Segurança

- O n8n **não fica exposto na internet**: escuta só em `127.0.0.1:5678` da EC2 e na rede interna do
  compose. O webhook também é interno: de fora, ninguém dispara o robô.
- O token da API (`/sonar/api/token-servico`) e a chave que cifra as credenciais do n8n
  (`/sonar/n8n/chave`, ou uma chave gerada e guardada na EC2 se o parâmetro não existir) vêm do
  deploy; nada disso fica no fluxo exportado.
- Credenciais extras (bot do Telegram, e-mail) são cadastradas no editor do n8n e ficam cifradas
  no volume dele, não no Git.

## Abrir o editor do n8n (opcional)

No seu computador (precisa do AWS CLI e do
[Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)):

```bash
aws ssm start-session --target <id-da-ec2> --document-name AWS-StartPortForwardingSession \
  --parameters portNumber=5678,localPortNumber=5678
```

O comando pronto sai de `terraform output abrir_o_n8n`. Abra http://localhost:5678 e crie o usuário
dono na primeira vez. Dá para ver cada execução (entrada e saída de cada nó).

## Testar ponta a ponta

1. No app, rode a demonstração "não parou" e aceite registrar a reclamação.
2. Em poucos segundos o app fala "Sua reclamação foi registrada com o protocolo SIM-...".
3. No Grafana, `sonar_rpa_avisos_total` conta os avisos da API ao robô.

## Cliente em Python (referência)

`sonar_rpa/` faz o mesmo ciclo em Python e tem testes do contrato (`pytest`). Serve para testar a
API sem o n8n.
