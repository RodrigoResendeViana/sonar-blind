# Próximos passos: as matérias numa solução só

O Sonar junta todas as matérias numa só jornada:

```
passageiro fala ─▶ IA GENERATIVA entende e acha a linha no Olho Vivo ─▶ "esperar a linha 8000-10"
      ─▶ VISÃO COMPUTACIONAL lê o letreiro de quem chega ─▶ MAKER LAB: o braço segue o letreiro
      ─▶ ônibus certo: LED + bipe "é o seu"      ônibus passou direto: RPA registra a reclamação
                                                  e o passageiro ouve o protocolo em segundos
```

## O que já funciona sem fazer nada além do deploy

| Parte | Estado |
|---|---|
| App, API, demonstração, monitoramento | no ar |
| IA generativa | liga sozinha no deploy (Ollama + agente + modelo `qwen2.5:3b`); se o LLM falhar, a API responde por regras |
| RPA | liga sozinho no deploy (n8n importa e publica o fluxo); a API avisa o robô na hora do "não parou" |
| Visão computacional | funciona **sem modelo treinado** (só OCR) com letreiro impresso; o modelo YOLO melhora |
| Maker Lab | firmware pronto e compilando; falta montar e calibrar |
| Relatórios | rascunhos em `docs/entregas/`, faltam prints e resultados |

## 0. Atualizar a AWS (Rodrigo, ~20 min)

1. **Merge** do PR deste branch na `main`. O pipeline publica as imagens e faz o deploy.
   - O primeiro deploy demora uns minutos a mais: ele baixa o modelo de IA (~2 GB).
   - Se falhar ao baixar `sonar-ia` do GHCR: GitHub → *Packages* → `sonar-ia` → *Package settings* →
     *Change visibility* → **Public**, e *Re-run* no Actions.
2. **Terraform** (CloudShell) — cria o usuário MQTT do braço e a chave do n8n:
   ```bash
   cd ~/sonar && git pull origin main
   cd infra/terraform/nuvem && export TF_DATA_DIR=/tmp/tf-nuvem
   terraform init -backend-config="bucket=sonar-tfstate-572213224291"
   terraform apply        # esperado: só criações (braco-demo e /sonar/n8n/chave); nada de destroy na EC2
   ```
   Depois, rode o deploy de novo (Actions → *Re-run all jobs*) para a ACL do MQTT incluir o braço.
3. **Token do Olho Vivo** (para linhas reais; sem ele, tudo funciona com a demonstração):
   `aws ssm put-parameter --name /sonar/olhovivo/token --type SecureString --value <token> --overwrite`
4. **Conferir**:
   - No app, ponto de demonstração, perguntar por voz "qual ônibus vai para o centro?".
   - Demonstração "não parou" → aceitar registrar → o app fala o protocolo `SIM-...` em segundos.
   - No Grafana, a memória da EC2 abaixo de ~85%.

Para desligar IA e RPA (economizar memória): `aws ssm put-parameter --name /sonar/compose/perfis
--type String --value nenhum --overwrite` e deploy.

## 1. Visão computacional

Detalhes: `visao/README.md`.

1. **Imprimir os letreiros** da maquete: `cd visao && pip install -r requirements.txt && python imprimir.py`.
2. **Testar sem modelo** no notebook (Windows): `cd edge && .\iniciar.ps1` e mexer o letreiro na
   frente da webcam. A janela mostra o que foi lido.
3. **Treinar com o sintético** (Colab com GPU): `python sintetico.py --quantidade 1500` e
   `python treinar.py`. Copiar `edge/modelos/letreiro.pt` para o notebook.
4. **Fotos reais** (150–300), rostos e placas borrados, rotuladas no Roboflow (classe `letreiro`), e
   treinar de novo juntando: `python treinar.py --dados dados/sintetico/letreiros.yaml dados/roboflow/data.yaml`.
5. **Medir**: métricas do `treinar.py` (sintético × sintético + reais) e 20 passagens na maquete
   (só OCR × YOLO). Preencher `docs/entregas/visao-computacional.md`.

## 2. IA generativa

Detalhes: `ia/README.md`.

1. Perguntar pelo app (voz) algumas vezes para "aquecer" e ver se responde rápido.
2. **Avaliar**: `cd ia && pip install httpx && python avaliar.py` (e `--com-olhovivo` com o token).
   Gera `ia/avaliacao/resultado.md`, a tabela do relatório.
3. Opcional: comparar `qwen2.5:3b` e `qwen2.5:1.5b` (parâmetro `/sonar/ia/modelo`) em acerto e tempo.
4. Prints: app respondendo, tabela da avaliação, Grafana (`sonar_ia_respostas_total` por modo).
   Preencher `docs/entregas/ia-generativa.md`.

## 3. RPA

Detalhes: `rpa/README.md`.

1. Testar o "não parou" pelo app (passo 0.4).
2. **Abrir o editor** do n8n pelo túnel do SSM (comando em `terraform output abrir_o_n8n`; precisa do
   AWS CLI e do Session Manager plugin no **seu** computador) para os prints das execuções.
3. Evoluir o canal (opcional para a nota, bom para o vídeo): e-mail para a ouvidoria (pode ser um
   e-mail da equipe), Telegram e Google Sheets. Exportar o fluxo para `rpa/n8n/` e abrir PR.
4. Preencher `docs/entregas/rpa.md`.

## 4. Maker Lab

Passo a passo completo (material, montagem, gravação, calibração, testes): `docs/maker-lab.md`.

1. Separar/comprar o material (ESP32, 2 servos + suporte pan-tilt, fonte 5 V, webcam, HC-SR04,
   LED, buzzer, botão, OLED).
2. Simular no Wokwi (braço, ponto e bordo) e gravar a tela.
3. Montar, gravar o firmware (`secrets.h` com Wi-Fi e senhas do Parameter Store) e calibrar o braço
   com `.\iniciar.ps1 -Braco`.
4. Montar a maquete (ponto, ônibus de papelão com o letreiro impresso).
5. Preencher `docs/entregas/maker-lab.md`.

## 5. Juntar tudo na demonstração

Roteiro do vídeo final (2 a 3 minutos):

1. O passageiro abre o app no ponto e pergunta por voz qual ônibus vai para o destino (**IA**).
2. Pede para esperar a linha; o LED do ponto pisca e o bipper do motorista toca (**Maker Lab**).
3. O "ônibus" chega; o braço gira e segue o letreiro, a câmera lê a linha (**Visão + Maker Lab**).
4. Primeira passagem: outra linha → o app diz "não é o seu".
5. Segunda passagem: a linha certa passa direto → o app pergunta se registra a reclamação →
   segundos depois o passageiro ouve o protocolo (**RPA**).
6. Fechar no Grafana e no pipeline verde (**Secure DevOps**).

## 6. Fechar as entregas

Rascunhos em `docs/entregas/`: trocar `[PRINT: ...]` e `[PREENCHER: ...]`, revisar contra o
enunciado de cada matéria e exportar para PDF.

## Depois

- **Big Data**: base anônima de esperas, passagens e reclamações (`GET /api/painel/indicadores`
  e a planilha do n8n): linhas que mais passam direto, horários, pontos críticos.
- **Business Development**: proposta para a SPTrans e a prefeitura, custo por ponto
  (`docs/custo.md`), modelo de implantação e o pitch.
