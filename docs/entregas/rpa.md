# Sonar — RPA

**FIAP · Global Solution 2026.2 · CitizenTech**
Grupo: [PREENCHER] · Integrantes (RM): [PREENCHER]
Repositório: https://github.com/RodrigoResendeViana/sonar-blind · Vídeo: [PREENCHER: link]

## 1. Problema

Quando um ônibus passa direto por uma pessoa com deficiência, a reclamação formal (156/SPTrans)
exige ligar ou preencher formulário com linha, prefixo, horário e local — informações que justamente
essa pessoa não consegue ver. Na prática, a reclamação não é feita e o problema some das estatísticas.

## 2. Solução

O Sonar já tem as evidências: a linha (Olho Vivo e câmera), o prefixo do ônibus avisado, o horário,
o tempo parado medido pelo ultrassom e se o motorista confirmou o aviso no bipper. Com o
**consentimento** do passageiro ("posso registrar a reclamação?"), um robô no **n8n** monta e registra
a reclamação e devolve o **protocolo**, que o app fala para o passageiro.

```
passageiro aceita ─▶ API cria a ocorrência ─▶ webhook interno ─▶ n8n
                                              n8n: buscar pendentes ─▶ conferir evidências ─▶ registrar ─▶ PATCH status + protocolo
                                                                                                              │
                                                                       app fala "protocolo SIM-..." ◀── API ◀─┘
```

| Nó do fluxo | O que faz |
|---|---|
| Aviso da API (webhook) | disparado na hora em que o passageiro consente (só na rede interna) |
| A cada 15 minutos | rede de segurança: pega o que o webhook não pegou |
| Buscar ocorrências pendentes | `GET /api/ocorrencias?status=pendente`, com token de serviço |
| Conferir e registrar | exige consentimento e linha; exige evidência (câmera com confiança ≥ 0,6 ou "ciente" do motorista); monta o texto e registra (MVP: protocolo simulado `SIM-...`) |
| Devolver status para a API | `PATCH /api/ocorrencias/{id}` com `enviada` + protocolo ou `inconclusiva` + motivo |

Arquivos: `rpa/n8n/ocorrencias.json` (fluxo), `api/sonar_api/rpa.py` (webhook),
`api/sonar_api/rotas/ocorrencias.py` (contrato).

## 3. Segurança e operação

- O n8n não fica exposto na internet (só `127.0.0.1` da EC2 e a rede interna do compose); o editor é
  acessado por túnel do AWS SSM.
- A API só aceita o robô com token de serviço (Parameter Store); a chave que cifra as credenciais do
  n8n também vem do Parameter Store.
- O fluxo é versionado no Git e importado/publicado a cada deploy (o repositório é a fonte da verdade).
- Sem consentimento, a ocorrência fica só no relatório anônimo: o robô não envia nada.

## 4. Resultados

| Cenário | Resultado |
|---|---|
| Ônibus passou direto, passageiro consentiu | protocolo falado em [PREENCHER] s |
| Sem evidência (sem câmera nem ciente) | `inconclusiva` com o motivo |
| n8n fora do ar | a API segue normal; a ocorrência é processada quando ele volta |

[PRINT: o fluxo no editor do n8n]
[PRINT: uma execução com sucesso (entrada e saída de cada nó)]
[PRINT: o app mostrando/falando o protocolo]
[PRINT: Grafana, `sonar_rpa_avisos_total`]

## 5. Próximos passos

- Trocar o registro simulado pelo canal real (formulário do SP156 ou e-mail da ouvidoria) e guardar o
  protocolo devolvido.
- Telegram para a equipe a cada reclamação e Google Sheets com o histórico (base para Big Data).
- Fluxo de erro do n8n marcando a ocorrência como `erro` para reprocessar.

## 6. Como testar

No app, demonstração "não parou" → aceitar registrar → o protocolo é falado em segundos.
Detalhes: `rpa/README.md`.
