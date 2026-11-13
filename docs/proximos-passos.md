# Próximos passos

## A jornada (o que o MVP faz)

```
[toque] "quero ir para o hospital"
   → o Sonar planeja: "pegue o DEMO-20 no ponto aqui do lado, desça no Centro e pegue o DEMO-30.
     O próximo DEMO-20 chega em 3 minutos. Quer ir?"                         (IA / planejador)
[toque] "sim"  → "vá até o ponto; quando chegar, diga 'cheguei'" (ou o GPS percebe a 40 m)
[toque] "cheguei" → o ponto apita, o LED pisca para o motorista, o Sonar Bordo toca  (Maker Lab)
   → a câmera lê o letreiro, o braço segue o ônibus: "DEMO-10, não é o seu" … "DEMO-20: é o seu" (Visão)
[toque] "embarquei" → no ônibus: "prepare-se, a próxima parada é o Centro" → "desça agora"
   → baldeação: o Sonar já avisa o próximo ponto … "você chegou"
se o ônibus passar direto: [toque] "quero reclamar" → n8n registra → "protocolo SIM-…" (RPA)
sem app ou sem internet: o botão do poste avisa todos os motoristas
```

## O que já funciona só com o deploy

| Parte | Estado |
|---|---|
| App com um botão, conversa por voz e plano de viagem | pronto (rede de demonstração em volta da maquete) |
| Linhas reais de São Paulo | pronto no código; falta subir o GTFS da SPTrans (passo 2) |
| Previsão em tempo real | pronta; falta o token do Olho Vivo (passo 2) |
| IA generativa (perguntas livres e planejamento por ferramenta) | no ar |
| RPA (reclamação por voz → n8n → protocolo) | no ar |
| Botão do poste | no firmware do Sonar Ponto e na tela "Ponto (simulado)" |
| Braço que segue o letreiro, ESP32-CAM opcional | firmware pronto; falta montar e calibrar |
| Visão | funciona só com OCR; o modelo YOLO melhora (passo 4) |

## 1. Publicar e testar a jornada (Rodrigo, ~15 min)

1. Merge do PR `jornada-por-voz` → o pipeline faz o deploy.
2. No celular (Chrome no Android ou Safari no iPhone), abra https://sonar.rodrigoviana.app.br,
   aceite o consentimento e permita o microfone.
3. Toque no botão e diga **"quero ir para o hospital"**; depois "sim", "cheguei", espere o ônibus,
   "embarquei". Para ouvir o app sem leitor de tela: "Mais opções" → "Ler as respostas em voz alta".
4. Teste a reclamação: "Mais opções" → "O ônibus passa direto"; repita a jornada e, quando ele
   passar, diga "quero reclamar". O protocolo chega em segundos.
5. Teste o botão do poste: tela "Ponto (simulado)" → "Botão do poste".

Se algo não falar o que devia, mande o que apareceu na tela.

## 2. Dados reais da SPTrans (opcional, conta muito na apresentação)

**Token do Olho Vivo** (previsão em tempo real): crie a conta e um aplicativo na área de
desenvolvedores da SPTrans e grave o token:

```bash
aws ssm put-parameter --name /sonar/olhovivo/token --type SecureString --value "SEU_TOKEN" --overwrite
```

**GTFS** (linhas e paradas, para planejar de qualquer lugar de São Paulo):

1. Na mesma área de desenvolvedores, baixe o GTFS (um `.zip`).
2. No CloudShell: menu Ações → Fazer upload de arquivo → escolha o zip. Depois:
   ```bash
   aws s3 mb s3://sonar-dados-572213224291          # só na primeira vez (bucket privado)
   aws s3 cp gtfs.zip s3://sonar-dados-572213224291/gtfs.zip
   URL=$(aws s3 presign s3://sonar-dados-572213224291/gtfs.zip --expires-in 604800)
   aws ssm put-parameter --name /sonar/gtfs/url --type SecureString --value "$URL" --overwrite
   ```
3. Rode o deploy de novo **logo em seguida** (o link do CloudShell vale poucas horas). O deploy
   baixa o arquivo uma vez e guarda na EC2; o log mostra "planejador com as linhas reais".
4. Teste: "quero ir para o Terminal Lapa" (o app pede a localização na primeira vez).

Na demonstração com a maquete, diga um destino da rede de exemplo (hospital, terminal, centro,
universidade, mercado) ou fale "exemplo" no destino: o plano sai da maquete.

## 3. Maker Lab

Tudo em `docs/maker-lab.md`: material, ligações, Wokwi, gravação e calibração.

1. **Sonar Ponto** com o botão do poste (GPIO 32), LED, buzzer e ultrassom.
2. **Sonar Braço** (2 servos, fonte 5 V externa) com a webcam presa na cabeça, ou a **ESP32-CAM**
   (`pio run -e camera`), que manda o vídeo sem fio para o notebook.
3. **Notebook do ponto**: `cd edge` e `.\iniciar.ps1 -Braco` (com a ESP32-CAM:
   `-Camera "http://IP:81/stream?t=TOKEN"`). Use o celular como roteador se a rede da faculdade
   bloquear o MQTT (porta 8883).
4. Calibrar o braço com o letreiro impresso (`python visao/imprimir.py`).

## 4. Visão computacional

`visao/README.md`: dataset sintético (sem rotular), fotos reais no Roboflow, treino no Colab,
métricas. O serviço da câmera usa o modelo sozinho quando `edge/modelos/letreiro.pt` existe.

## 5. IA generativa

`cd ia && python avaliar.py` → `ia/avaliacao/resultado.md` (tabela do relatório). As perguntas
agora incluem planejamento ("preciso ir ao hospital, como eu faço?").

## 6. Vídeo (2–3 min)

1. O passageiro toca no botão e diz o destino; o Sonar fala o plano com baldeação.
2. "Cheguei": o ponto da maquete apita e pisca; o Sonar Bordo toca; o motorista aperta "ciente".
3. O ônibus de papelão chega: o braço segue o letreiro; "não é o seu"; depois "é o seu".
4. "Embarquei" → "prepare-se para descer" → baldeação → "você chegou".
5. Outra rodada: o ônibus passa direto → "quero reclamar" → protocolo falado.
6. O botão do poste sem o app; fechar no Grafana e no pipeline verde.

## 7. Relatórios

Rascunhos em `docs/entregas/`: trocar `[PRINT: ...]` e `[PREENCHER: ...]`, revisar contra o
enunciado de cada matéria e exportar para PDF.

## Depois

- **Big Data**: base anônima de viagens planejadas, esperas, passagens e reclamações (linhas que
  mais passam direto, horários, pontos críticos, pedidos pelo botão).
- **Business Development**: proposta para a SPTrans e a prefeitura, custo por ponto
  (`docs/custo.md`), modelo de implantação e o pitch.
