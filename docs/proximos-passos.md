# Próximos passos: as matérias numa solução só

O Sonar junta todas as matérias numa só jornada:

```
passageiro fala ─▶ IA GENERATIVA entende e acha a linha no Olho Vivo ─▶ "esperar a linha 8000-10"
      ─▶ VISÃO COMPUTACIONAL lê o letreiro de quem chega ─▶ MAKER LAB: o braço segue o letreiro
      ─▶ ônibus certo: LED + bipe "é o seu"      ônibus passou direto: RPA registra a reclamação
                                                  e o passageiro ouve o protocolo
```

O código de cada parte já está no repositório e testado no pipeline. O que falta é, na maior parte,
trabalho fora do código: dataset, montagem, configuração na AWS, testes reais e evidências.
Os passos estão em ordem; dentro de cada matéria, a equipe pode trabalhar em paralelo às outras.

---

## 0. Ligar as peças novas na AWS (Rodrigo)

1. **Fazer o merge** do PR `materias → main`. O pipeline publica a imagem nova `sonar-ia` no GHCR.
2. **Terraform** (CloudShell), para criar a chave do n8n e o usuário MQTT do braço:
   ```bash
   cd ~/sonar && git pull origin main
   cd infra/terraform/nuvem && export TF_DATA_DIR=/tmp/tf-nuvem
   terraform init -backend-config="bucket=sonar-tfstate-572213224291"
   terraform apply        # esperado: + /sonar/n8n/chave, + /sonar/mqtt/usuarios/braco-demo
   ```
3. **Ligar a IA e o RPA** (Parameter Store):
   ```bash
   aws ssm put-parameter --name /sonar/compose/perfis --type String --value ia,rpa --overwrite
   aws ssm put-parameter --name /sonar/ia/url --type String --value http://ia:8100 --overwrite
   aws ssm put-parameter --name /sonar/ia/modelo --type String --value qwen2.5:3b --overwrite
   ```
4. **Rodar o deploy de novo** (Actions → último run da `main` → *Re-run all jobs*). Ele sobe o
   Ollama, o agente e o n8n, baixa o modelo (~2 GB, alguns minutos) e importa o fluxo do n8n.
5. Se o deploy falhar ao baixar `sonar-ia` do GHCR: GitHub → *Packages* → `sonar-ia` →
   *Package settings* → *Change visibility* → **Public** (igual às outras imagens).
6. Conferir: `https://sonar.rodrigoviana.app.br/api/readyz` mostra a IA configurada, e no
   Grafana a memória da EC2 fica abaixo de ~85%.

## 1. Visão computacional (ler o letreiro)

Código pronto: `edge/` (YOLO + OCR + votação em 3 quadros, publica a linha lida e a posição
do letreiro) e `visao/` (treino). Falta o modelo.

1. **Montar o dataset**: 150 a 300 imagens de letreiros de ônibus de SP (fotos na rua,
   *frames* de vídeos, letreiros impressos para a maquete). Variar luz, distância e ângulo.
2. **Rotular** no Roboflow (classe única `letreiro`) e exportar no formato YOLOv8/YOLO11
   (treino/validação/teste ≈ 70/20/10). Borrar rostos e placas antes (LGPD).
3. **Treinar**: `cd visao && python treinar.py --dados dados/letreiros.yaml --epocas 50`
   (no Colab com GPU, se o notebook for lento). Copiar o `best.pt` para `edge/modelos/letreiro.pt`.
4. **Testar na webcam**:
   `python -m sonar_camera --parada demo --linhas DEMO-10,DEMO-20 --modo webcam --modelo modelos/letreiro.pt --mirar-sempre`
5. **Medir**: mAP50, precisão e revocação do conjunto de teste; e a taxa de acerto da linha lida
   ponta a ponta (YOLO + OCR + votação) em 20 passagens de letreiros impressos.
6. **Evidências**: gráficos do treino, matriz de confusão, tabela de métricas, vídeo da leitura.

## 2. IA generativa (entender a voz e achar o ônibus)

Código pronto: `ia/` (agente com LLM local no Ollama e ferramentas `buscar_linha` e
`previsao_parada`, que leem o Olho Vivo pela API) e a voz no app (Web Speech API).

1. **Token do Olho Vivo** (se ainda não tiver): cadastro em sptrans.com.br/desenvolvedores, e
   `aws ssm put-parameter --name /sonar/olhovivo/token --type SecureString --value <token> --overwrite`.
2. **Testar pelo app**: no ponto de demonstração, perguntar por voz "quando chega a DEMO-10?" e
   "qual ônibus vai para a Lapa?".
3. **Montar o conjunto de avaliação**: 15 a 20 perguntas com a resposta esperada: linha certa,
   destino, linha que não passa no ponto, pergunta fora do assunto, pergunta ambígua.
4. **Medir** acerto e latência (`sonar_ia_latencia_segundos` no Grafana). Se ficar lento, testar
   `qwen2.5:1.5b`; se errar muito, ajustar o texto de `INSTRUCOES` em `ia/sonar_ia/agente.py`.
5. **Evidências**: tabela da avaliação, prints das respostas, o caso em que o modelo inventaria
   e o guarda-corpo devolve `nao_consta`, e a explicação do *tool calling* (README de `ia/`).

## 3. RPA (registrar a reclamação automaticamente)

Código pronto: fluxo do n8n em `rpa/n8n/ocorrencias.json`, importado pelo deploy.

1. **Abrir o n8n** pelo túnel do SSM (comando em `terraform output abrir_o_n8n`; precisa do AWS
   CLI e do Session Manager plugin no seu computador) e acessar http://localhost:5678.
2. Criar o usuário dono, abrir o fluxo **"Sonar - ocorrências de ônibus que não parou"** e ativá-lo.
3. **Teste ponta a ponta**: no app, demonstração "não parou" → aceitar registrar → no n8n,
   *Rodar agora (demo)* → o app fala o protocolo `SIM-...`.
4. **Evoluir o canal**: trocar o nó "Conferir e registrar" (simulado) por um **Send Email** para a
   ouvidoria (pode ser um e-mail da equipe, para a demo) e acrescentar **Telegram** e
   **Google Sheets** (histórico das reclamações).
5. Exportar o fluxo final (menu ⋯ → *Download*) para `rpa/n8n/ocorrencias.json` e abrir PR.
6. **Evidências**: print do fluxo, execuções com sucesso e com `inconclusiva`, e o e-mail/Telegram.

## 4. Maker Lab (braço que segue o letreiro)

Código pronto: firmware `firmware/src/braco/` (cabeça pan-tilt), simulação
`firmware/wokwi/braco/` e a posição do letreiro publicada pela visão em `sonar/parada/demo/mira`.

1. **Comprar/separar**: ESP32 DevKit, 2 servos SG90 ou MG90S, suporte pan-tilt, fonte 5 V / 2 A,
   potenciômetro 10 kΩ (opcional), jumpers, protoboard e uma webcam USB.
2. **Simular no Wokwi**: `pio run -e braco_wokwi`, abrir `wokwi/braco/diagram.json` e girar o
   potenciômetro (modo manual). Gravar a tela como primeira evidência.
3. **Montar**: servos nos GPIO 18 (pan) e 19 (tilt), V+ dos servos na **fonte externa**, GND
   comum com o ESP32; prender a webcam na cabeça. Ligações em `firmware/README.md`.
4. **Gravar**: copiar `include/secrets.example.h` para `include/secrets.h`, preencher o Wi-Fi e a
   senha do `braco-demo` (`aws ssm get-parameter --name /sonar/mqtt/usuarios/braco-demo --with-decryption ...`)
   e rodar `pio run -e braco -t upload`.
5. **Testar sem visão**: `python -m sonar_camera --parada demo --linhas DEMO-10 --mirar-sempre` e
   digitar `DEMO-10@0.1`, `DEMO-10@0.9`: a cabeça vira para os lados.
6. **Testar com visão**: mesmo comando com `--modo webcam`, mover um letreiro impresso na frente
   da câmera e ajustar `GANHO_PAN`, `ZONA_MORTA` e `VELOCIDADE_MAX` em `include/config.h` até
   seguir sem tremer.
7. **Maquete**: ponto de ônibus com o Sonar Ponto (ultrassom, LED, buzzer) e o braço; um "ônibus"
   de papelão com o letreiro impresso passando na frente.
8. **Evidências**: esquema elétrico, lista de materiais com custo, fotos da montagem, vídeo do Wokwi
   e vídeo do braço seguindo o letreiro.

## 5. Juntar tudo na demonstração

Roteiro do vídeo final (2 a 3 minutos):

1. O passageiro abre o app no ponto e pergunta por voz qual ônibus vai para o destino (**IA**).
2. Pede para esperar a linha; o LED do ponto pisca para o motorista e o bipper avisa (**Maker Lab**).
3. O "ônibus" chega; o braço gira e segue o letreiro, a câmera lê a linha (**Visão + Maker Lab**).
4. Primeira passagem: outra linha → o app diz "não é o seu".
5. Segunda passagem: a linha certa passa direto → o app pergunta se registra a reclamação →
   o n8n registra e o passageiro ouve o protocolo (**RPA**).
6. Fechar no Grafana e no pipeline verde (**Secure DevOps**).

## 6. Fechar as entregas

Para cada matéria: um PDF com problema, solução, arquitetura (a parte daquela matéria no
diagrama geral), como testar, evidências e o link do repositório e do vídeo.

## Depois

- **Big Data**: base anônima de esperas, passagens e reclamações (`GET /api/painel/indicadores`
  e a planilha do n8n): linhas que mais passam direto, horários, pontos críticos.
- **Business Development**: proposta para a SPTrans e a prefeitura, custo por ponto
  (`docs/custo.md`), modelo de implantação e o pitch.
