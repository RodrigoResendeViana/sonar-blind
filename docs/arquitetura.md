# Arquitetura

Três vistas, da mais geral para a mais detalhada: o sistema inteiro, o que roda dentro da EC2 e o
caminho de um commit até o ar.

## 1. Visão geral

```mermaid
flowchart TB
  subgraph rua["Na rua e no ônibus"]
    direction LR
    PAS["<b>Passageiro cego</b><br/>app de voz no celular"]
    PONTO["<b>Ponto de ônibus</b><br/>Sonar Ponto, câmera<br/>com visão e braço"]
    BORDO["<b>Ônibus</b><br/>Sonar Bordo,<br/>o bipper do motorista"]
    PAS ~~~ PONTO ~~~ BORDO
  end

  subgraph github["GitHub"]
    direction LR
    GHA["<b>Actions</b><br/>Gitleaks, Semgrep,<br/>testes e Trivy"] --> GHCR[("<b>GHCR</b><br/>imagens")]
  end

  subgraph aws["AWS us-east-1 · tudo criado por Terraform"]
    direction LR
    SSM["<b>SSM e Parameter Store</b><br/>deploy sem SSH<br/>e segredos"]
    subgraph ec2["EC2 · docker compose"]
      direction LR
      ENT["<b>Entrada</b><br/>Caddy: HTTPS 443<br/>Mosquitto: MQTT TLS 8883"]
      NUC["<b>API + Postgres</b><br/>conversa, planejador<br/>e esperas"]
      INT["<b>IA generativa e RPA</b><br/>Ollama e n8n"]
      MON["<b>Monitoramento</b><br/>Prometheus, Grafana<br/>e Alertmanager"]
      ENT --> NUC --> INT
      MON -.->|métricas| NUC
    end
    SSM -->|deploy| ec2
  end

  subgraph fora["Serviços externos"]
    direction LR
    SPT["<b>SPTrans</b><br/>Olho Vivo e GTFS"] ~~~ OSM["<b>OpenStreetMap</b><br/>endereços"] ~~~ TG["<b>Telegram</b><br/>alertas"]
  end

  rua <-->|"HTTPS 443<br/>MQTT TLS 8883"| aws
  github -->|"deploy: OIDC + SSM<br/>imagens do GHCR"| aws
  aws -->|"previsão, endereços<br/>e alertas"| fora

  classDef pessoa fill:#e8f5e9,stroke:#2e7d32,color:#1b1f24
  classDef nuvem fill:#fff3e0,stroke:#e65100,color:#1b1f24
  classDef git fill:#eceff1,stroke:#455a64,color:#1b1f24
  classDef externo fill:#e3f2fd,stroke:#1565c0,color:#1b1f24
  class PAS,PONTO,BORDO pessoa
  class SSM,ENT,NUC,INT,MON nuvem
  class GHA,GHCR git
  class SPT,OSM,TG externo
  style rua fill:#f6fbf6,stroke:#2e7d32,color:#1b1f24
  style github fill:#f7f8f9,stroke:#455a64,color:#1b1f24
  style aws fill:#fffaf3,stroke:#e65100,color:#1b1f24
  style ec2 fill:#ffffff,stroke:#e65100,stroke-dasharray:4 3,color:#1b1f24
  style fora fill:#f5f9ff,stroke:#1565c0,color:#1b1f24
```

**Por que assim.** A EC2 é a única máquina exposta à internet (portas 80, 443 e 8883), e o
monitoramento roda nela, lendo as métricas pela rede interna do compose. Os ESP32 e o notebook da
câmera só fazem conexões de saída, então não precisam de porta aberta. O pipeline publica sem SSH e
sem chave da AWS guardada: troca o token OIDC do GitHub por credenciais de uma hora, que só podem
mandar comando para esta EC2.

## 2. Dentro da EC2

```mermaid
flowchart TB
  subgraph quem["Quem chega"]
    direction LR
    USU["<b>App e navegador</b><br/>HTTPS 443"] ~~~ DISP["<b>ESP32 e câmera</b><br/>MQTT TLS 8883"]
  end

  subgraph ec2["EC2 · docker compose · portas abertas: só 80, 443 e 8883"]
    direction LR
    subgraph borda["Borda"]
      direction LR
      CADDY["<b>web</b> · Caddy<br/>HTTPS, app, /api e /grafana"] ~~~ MQ["<b>mqtt</b> · Mosquitto<br/>senha e ACL<br/>por dispositivo"]
    end
    subgraph app["Aplicação"]
      direction LR
      API["<b>api</b> · FastAPI<br/>conversa e esperas"] --> DB[("<b>db</b><br/>Postgres")]
    end
    subgraph intel["IA e RPA"]
      direction LR
      IA["<b>ia</b> · agente de IA"] --> OL["<b>ollama</b><br/>LLM local"]
      N8["<b>n8n</b> · robô de RPA<br/>editor só por túnel do SSM"]
    end
    subgraph mon["Monitoramento"]
      direction LR
      GRA["<b>grafana</b><br/>painel"] --> PROM["<b>prometheus</b><br/>coleta e regras"] --> AM["<b>alertmanager</b>"]
      EXP["<b>blackbox</b>: site visto de fora<br/><b>node-exporter</b>: CPU, RAM, disco"]
    end
    borda -->|"/api e MQTT"| app
    app -->|"perguntas e webhook"| intel
    mon -.->|"coleta /metrics"| app
  end

  TG["<b>Telegram</b><br/>alertas"]
  quem --> ec2
  mon --> TG

  classDef c fill:#fff3e0,stroke:#e65100,color:#1b1f24
  classDef e fill:#e8f5e9,stroke:#2e7d32,color:#1b1f24
  classDef x fill:#e3f2fd,stroke:#1565c0,color:#1b1f24
  class CADDY,MQ,API,DB,IA,OL,N8,GRA,PROM,AM,EXP c
  class USU,DISP e
  class TG x
  style ec2 fill:#fffaf3,stroke:#e65100,color:#1b1f24
  style quem fill:#f6fbf6,stroke:#2e7d32,color:#1b1f24
  style borda fill:#ffffff,stroke:#e65100,stroke-dasharray:4 3,color:#1b1f24
  style app fill:#ffffff,stroke:#e65100,stroke-dasharray:4 3,color:#1b1f24
  style intel fill:#ffffff,stroke:#e65100,stroke-dasharray:4 3,color:#1b1f24
  style mon fill:#ffffff,stroke:#e65100,stroke-dasharray:4 3,color:#1b1f24
```

- **Borda:** só o Caddy (80 e 443) e o Mosquitto (8883) recebem conexões de fora. O Caddy serve o
  app e repassa `/api` para a API e `/grafana` para o Grafana; o Mosquitto exige TLS, senha e ACL
  por dispositivo.
- **Aplicação:** a API e o Postgres. O banco não publica porta nenhuma.
- **IA e RPA:** o agente de IA usa o LLM local (Ollama) e consulta a API pelas ferramentas; o n8n
  recebe o webhook da API, e o editor dele só abre por túnel do SSM (porta presa em 127.0.0.1).
- **Monitoramento:** o Prometheus coleta a API, a máquina (node-exporter) e o site visto de fora
  (blackbox); o Alertmanager manda os alertas para o Telegram; o Grafana mostra os sinais de ouro.

## 3. Do push ao ar

```mermaid
flowchart LR
  PUSH(["<b>push</b><br/>em qualquer branch"]) --> VER["<b>Verificações</b><br/>Gitleaks · Semgrep · testes<br/>Terraform · Trivy na IaC<br/>e nas dependências"]
  VER --> IMG["<b>Imagens</b><br/>build · Trivy · SBOM"]
  IMG -->|"só na main"| GHCR[("<b>GHCR</b>")]
  GHCR --> DEP["<b>Deploy</b><br/>OIDC → SSM<br/>deploy.sh na EC2"]
  DEP --> POS["<b>Depois do deploy</b><br/>teste de fumaça<br/>e ZAP baseline"]
  VER -.->|"achou problema"| BAR(["<b>Barrado</b><br/>nada é publicado"])
  IMG -.->|"CVE alta ou crítica"| BAR

  classDef pare fill:#ffebee,stroke:#c62828,color:#1b1f24
  classDef git fill:#eceff1,stroke:#455a64,color:#1b1f24
  classDef nuvem fill:#fff3e0,stroke:#e65100,color:#1b1f24
  class PUSH,VER,IMG,GHCR git
  class DEP,POS nuvem
  class BAR pare
```

Tudo isso está em [`.github/workflows/ci-cd.yml`](../.github/workflows/ci-cd.yml); um exemplo real de
execução barrada e da corrigida está em [`docs/execucao-barrada.md`](execucao-barrada.md).

## Fluxo de uma viagem

No perfil do passageiro, o app tem um botão só: a pessoa diz o destino (`POST /conversa`), a API
acha o lugar (rede conhecida ou OpenStreetMap), as paradas perto dela e do destino e o melhor
caminho com até uma baldeação (GTFS da SPTrans; na demonstração, uma rede fictícia em volta da
maquete), e fala o plano com a previsão do Olho Vivo. Quando o GPS mostra que a pessoa chegou ao
ponto (ou ela diz "cheguei"), a API abre a espera e publica `ativar` no tópico retido do ponto: o
Sonar Ponto pisca o LED e apita, a API acompanha o Olho Vivo e avisa o Sonar Bordo do ônibus certo
a ~4 minutos, o motorista aperta "ciente" (no Sonar Bordo ou no perfil do motorista), a câmera lê o
letreiro (e o braço segue o ônibus), o Sonar Ponto junta com o ultrassom e publica a passagem, e a
API fala "é o seu" pelo SSE. Sem o Sonar Ponto, a própria câmera publica a passagem. Depois do
"embarquei", o GPS avisa a hora de descer e a baldeação. Se o ônibus passa direto, a pessoa diz
"quero reclamar" e o robô de RPA registra e devolve o protocolo. Sem app, o botão do poste avisa
os motoristas de todas as linhas.

## Como as matérias se encaixam

IA generativa responde perguntas livres e planeja viagens por ferramentas (`ia/`), ao lado da
conversa por regras que conduz a viagem (`api/sonar_api/conversa.py`); Visão computacional lê o
letreiro e acha onde ele está no quadro (`edge/`, `visao/`); Maker Lab segue o letreiro com o braço
e avisa no ponto e na cabine (`firmware/`); RPA transforma o "não parou" em reclamação com
protocolo (`rpa/`); Secure DevOps entrega e vigia tudo (`infra/`, `.github/`). Cada parte tem uma
rede de segurança: sem LLM, a API responde por regras; sem modelo treinado, a câmera usa só OCR;
sem webhook, o robô roda a cada 15 minutos; sem câmera, o Sonar Ponto decide pelo ultrassom e avisa
"sem confirmação visual".

## Segurança em camadas

| Camada | Controle |
|---|---|
| Borda | só 80/443/8883; HTTPS automático; HSTS, CSP restritiva, Permissions-Policy |
| Aplicação | validação de entrada (Pydantic), limite de requisições, token só para o robô, métricas só na rede interna, Grafana com login |
| Dispositivos | usuário e senha por dispositivo, ACL por tópico, TLS com as raízes da Let's Encrypt fixadas no firmware |
| Containers | sem root, `no-new-privileges`, `cap_drop: ALL`, sistema de arquivos só leitura, limite de memória |
| Nuvem | IMDSv2 com hop limit 1 (containers não pegam a credencial da EC2), disco cifrado, papéis IAM mínimos, segredos no Parameter Store |
| Pipeline | Gitleaks, Semgrep, Trivy (IaC, dependências e imagens), SBOM, ações fixadas em versões que rodam no Node 24, Dependabot |
