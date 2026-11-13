# Contratos de integração

Cada equipe trabalha contra estes contratos; se um lado atrasa, o outro usa o simulador.
A especificação completa da API está em [`openapi.json`](openapi.json) e, com o sistema no ar,
em `https://sonar.rodrigoviana.app.br/api/docs`.

## API (HTTPS, prefixo `/api`)

| Rota | Quem usa | Para quê |
|---|---|---|
| `GET /healthz` | pipeline, healthcheck | vivo (teste de fumaça) |
| `GET /readyz` | deploy | banco, Olho Vivo, MQTT e IA configurados |
| `GET /paradas`, `GET /paradas/proxima?lat=&lon=` | app | paradas com Sonar Ponto; a localização não é gravada |
| `GET /paradas/{id}/previsao` | app, IA | previsão do Olho Vivo (cache de 30 s) ou dados de demonstração |
| `GET /linhas?termo=` | agente de IA | busca de linha por número ou destino (Olho Vivo) |
| `POST /conversa` | app (tela de voz) | um turno da conversa: `{sessao, evento: abrir \| fala \| posicao \| tick, texto, lat, lon, cenario_demo}` → `{sessao, estado, fala, espera_id, plano, trecho, acompanhar, intervalo_s, pedir_localizacao?}` |
| `GET /viagens/planejar?destino=&lat=&lon=` | agente de IA | plano de viagem (até uma baldeação) e a frase pronta |
| `POST /ia/perguntar` | app, conversa | pergunta livre (contrato abaixo) |
| `POST /esperas` | app ("Cheguei") | abre a espera e liga o Sonar Ponto |
| `GET /esperas/{id}` | app | estado da espera |
| `GET /esperas/{id}/eventos` | app | **Server-Sent Events** com as falas (abaixo) |
| `POST /esperas/{id}/localizar` | app | bip do Sonar Ponto para achar o poste |
| `POST /esperas/{id}/embarque` | app ("Embarquei") | `{origem, horario}`; a API cruza com a passagem que a câmera registrou |
| `POST /esperas/{id}/nao-parou` | app | `{consentimento}`; vira ocorrência para o robô |
| `POST /esperas/{id}/cancelar` | app | encerra a espera |
| `GET /painel/indicadores` | painel da cidade | números agregados, sem dado pessoal |
| `GET /ocorrencias?status=pendente`, `PATCH /ocorrencias/{id}` | robô de RPA | `Authorization: Bearer <token>` (Parameter Store `/sonar/api/token-servico`) |
| `POST /demo/esperas` | app, avaliador | `{cenario: embarque \| nao_parou \| maquete}`: a jornada em ~2 min |
| `/simulador/...` | telas Motorista e Ponto | gêmeos digitais do Sonar Bordo e do Sonar Ponto |

O app manda o cabeçalho `X-Sonar-Usuario` com um id anônimo do aparelho; a API guarda só
o SHA-256 dele com sal.

### Pergunta por voz (App → API → IA)

Entrada: `{"texto": "quero pegar a linha 8000-10", "parada_id": "itaquera-01"}`

Saída:

```json
{
  "status": "ok",
  "resposta_falada": "A linha 8000-10, sentido Terminal Lapa, chega em 4 minutos no ponto ... Fonte: Olho Vivo.",
  "acao": {"tipo": "esperar", "parada_id": "itaquera-01", "linhas": ["8000-10"]},
  "fontes": ["olhovivo:previsao:4200953"],
  "confianca": 0.9
}
```

`status` é `ok` ou `nao_consta`. Se `SONAR_IA_URL` estiver definido, a API repassa a pergunta
para `POST {SONAR_IA_URL}/perguntar` (o agente da equipe de GenAI) e valida a resposta contra
este esquema; resposta fora do esquema ou demora acima de 20 s vira `nao_consta` com
"tente de novo". Sem o agente, um responder por regras atende só o que está no cadastro e na
previsão.

### Eventos da espera (SSE)

Cada mensagem é `{"id", "tipo", "fala", "dados", "em"}`. O app põe a `fala` na região
`aria-live` (o leitor de tela lê) e vibra conforme `dados.vibrar`. O primeiro evento é
`{"tipo": "estado", "dados": <espera>}`. Ao reconectar, o navegador manda o `Last-Event-ID` e
recebe só o que perdeu.

| tipo | quando |
|---|---|
| `ponto_ativado` | espera aberta ("Você está no ponto certo...") |
| `previsao` | a previsão da linha mudou |
| `aviso_enviado`, `motorista_ciente` | aviso ao Sonar Bordo e o "ciente" do motorista |
| `onibus_chegando` | `dados.e_o_seu`: `true` (vibração longa), `false` ("não é o seu"), `null` (sem leitura da câmera) |
| `onibus_passou_direto` | a linha certa passou sem parar; o app pergunta se registra |
| `perguntar_embarque`, `perguntar_parou` | 45 s e 3 min depois da passagem sem "embarquei" |
| `embarque_confirmado` | `dados.validado_por_camera` |
| `ocorrencia_registrada`, `ocorrencia_protocolo`, `ocorrencia_inconclusiva` | caminho do "não parou" |
| `sem_confirmacao_visual`, `ponto_offline`, `olhovivo_indisponivel` | falhas, sempre faladas |
| `cancelada`, `expirada` | fim da espera |

## MQTT (Mosquitto na EC2, TLS na porta 8883)

Cada dispositivo tem usuário e senha próprios (`ponto-<parada>`, `camera-<parada>`,
`braco-<parada>`, `bordo-<prefixo>`) e a ACL só deixa cada um ler e escrever nos seus tópicos.

| Tópico | De → para | Conteúdo |
|---|---|---|
| `sonar/parada/{id}/cmd` | API → Sonar Ponto e câmera (retido) | `{"acao":"ativar","espera_id","linhas_alvo":[...],"expira_em"}`, `{"acao":"desativar"}`, `{"acao":"localizar"}`, `{"acao":"config","limiar_cm":15}` |
| `sonar/parada/{id}/visao` | câmera → Sonar Ponto | `{"linha_lida","confianca","passou_em"}` (só texto; nenhuma imagem) |
| `sonar/parada/{id}/evento` | Sonar Ponto → API | passagem: `{"espera_id","linha_lida","confianca","passou_em","tempo_parado_s","parou","camera_ok"}`; botão do poste: `{"tipo":"botao","em"}` (a API avisa os motoristas de todas as linhas do ponto por 10 min) |
| `sonar/parada/{id}/status` | Sonar Ponto → API (retido, 30 s) | `{"online","estado","rssi","uptime_s","fila","camera_ok","versao"}`; a queda vira `{"online":false}` (testamento MQTT) |
| `sonar/parada/{id}/camera/status` | câmera → API e Ponto (retido) | `{"online","ativa"}` |
| `sonar/parada/{id}/mira` | câmera → braço (até ~7/s) | `{"alvo":true,"x":0.42,"y":0.5,"linha":"DEMO-10"}` (centro do letreiro, 0 a 1) ou `{"alvo":false}` quando o letreiro some por 1 s |
| `sonar/parada/{id}/braco/status` | braço → API (retido) | `{"online","modo","pan","tilt"}` |
| `sonar/onibus/{prefixo}/alerta` | API → Sonar Bordo | `{"espera_id","parada_nome","paradas_ate","linha"}` |
| `sonar/onibus/{prefixo}/ciente` | Sonar Bordo → API | `{"espera_id","horario"}` |
| `sonar/onibus/{prefixo}/status` | Sonar Bordo → API (retido) | sinal de vida |

O aviso vai para o prefixo do ônibus que o Olho Vivo prevê chegar primeiro, quando faltam até
4 minutos (cerca de 2 paradas; `paradas_ate` é essa estimativa).

## Conversa por voz (app ↔ API)

O app só tem um botão. Cada frase vira `POST /conversa {"evento":"fala","texto":"quero ir para o hospital"}`;
a resposta traz a `fala` (o app lê pelo leitor de tela ou pela voz do navegador) e o `estado`:

`inicio` → `confirmar_plano` ("quer ir?") → `indo_ao_ponto` → `no_ponto` (espera aberta; os avisos do
ônibus chegam pelo SSE da espera) → `a_bordo` → (baldeação: `no_ponto` de novo) → `chegou`.
Se o ônibus passa direto: `apos_ocorrencia` (protocolo pelo SSE; "esperar de novo" volta a `no_ponto`).

Com `acompanhar: true`, o app manda `{"evento":"posicao","lat","lon"}` (ou `tick`) a cada
`intervalo_s`: é assim que a API percebe que a pessoa chegou ao ponto (40 m) e avisa a hora de descer
(450 m: "prepare-se"; 70 m: "desça agora"). Na demonstração, a viagem é simulada pelo tempo.
Se a API precisar da localização, responde `pedir_localizacao: true` e `repetir_texto`.

A sessão fica na memória da API (até 6 h) e a localização não vai para o banco.

## Linhas (API ↔ agente de IA)

`GET /api/linhas?termo=lapa` devolve `{"fonte": "olhovivo" | "demonstracao", "linhas": [{"codigo", "origem",
"destino", "sentido", "codigo_interno", "circular"}]}` (Olho Vivo `/Linha/Buscar`, um item por sentido).
Sem token do Olho Vivo, busca nas linhas cadastradas das paradas.

## Ocorrências (API ↔ robô de RPA)

`GET /api/ocorrencias?status=pendente` devolve as reclamações com consentimento, com as
evidências: parada (com o código da SPTrans), linha, prefixo avisado, horário e tempo parado da
passagem, confiança da leitura, horário do aviso e do "ciente". O robô confere e responde com
`PATCH /api/ocorrencias/{id}` e `{"status": "enviada", "protocolo": "..."}` (ou `inconclusiva`,
`duplicada`, `erro`); o app fala o protocolo para o usuário.

Gatilho: assim que o usuário consente, a API chama `POST {SONAR_RPA_WEBHOOK_URL}` com
`{"ocorrencia_id": 12}` (no deploy, o webhook interno do n8n), e o robô processa na hora. O robô
também lê as pendentes a cada 15 minutos, então um aviso perdido só atrasa, não perde a ocorrência.

Status: `aguardando_consentimento` → `pendente` (sim) ou `anonima` (não) → `em_processamento`
→ `enviada` / `inconclusiva` / `duplicada` / `erro`; `descartada` quando o usuário embarcou.
