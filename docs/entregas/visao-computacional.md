# Sonar — Visão Computacional

**FIAP · Global Solution 2026.2 · CitizenTech**
Grupo: [PREENCHER] · Integrantes (RM): [PREENCHER]
Repositório: https://github.com/RodrigoResendeViana/sonar-blind · Vídeo: [PREENCHER: link]

## 1. Problema

Uma pessoa cega no ponto de ônibus não consegue ler o letreiro de quem chega, e o motorista nem
sempre percebe que ela está esperando. Ela depende de perguntar a desconhecidos ou de "dar sinal"
para todo ônibus. O Sonar é um copiloto de voz que avisa "é o seu" quando a linha certa chega.

A parte de visão computacional responde à pergunta central: **qual linha é esse ônibus que está
chegando?**

## 2. Solução

Uma câmera no ponto (webcam ligada a um notebook, na maquete) acha o letreiro no quadro, lê o texto
e publica só a linha lida (`{"linha_lida": "8000-10", "confianca": 0.91}`) para o Sonar Ponto e para
a API. **Nenhuma imagem sai do notebook** e a câmera só fica ligada enquanto alguém está esperando.

```
quadro ─▶ localizar o letreiro ─▶ OCR ─▶ casar com as linhas da parada ─▶ votação de 3 quadros ─▶ MQTT
              │                                                                  
              └─▶ rastreador (entre detecções) ─▶ posição do letreiro ─▶ braço do Maker Lab
```

| Etapa | Como | Arquivo |
|---|---|---|
| Localizar | YOLO11n treinado para a classe `letreiro`; sem modelo, o próprio EasyOCR acha os textos | `edge/sonar_camera/detectores.py` |
| Ler | EasyOCR (pt/en) só no recorte, com lista de caracteres permitidos | idem |
| Corrigir o OCR | vocabulário restrito (só as linhas da parada), troca de O/0, I/1, S/5, semelhança de texto | `edge/sonar_camera/votacao.py` |
| Confirmar | a mesma linha em 3 quadros seguidos; não repete a mesma linha por 60 s | idem |
| Seguir | correlação normalizada (`cv2.matchTemplate`) numa janela em volta da última posição | `edge/sonar_camera/rastreador.py` |

## 3. Dataset e treino

- **Sintético** (`visao/sintetico.py`): [PREENCHER: N] imagens 640x640 geradas com letreiros LED e
  impressos, com e sem a frente do ônibus, perspectiva, desfoque, ruído, variação de luz, textos que
  não são letreiro e ~10% de imagens sem letreiro. O rótulo é exato (a caixa vem da própria geração).
- **Fotos reais**: [PREENCHER: N] fotos rotuladas no Roboflow (classe única `letreiro`), com rostos e
  placas borrados antes do upload (LGPD).
- **Treino** (`visao/treinar.py`): YOLO11n pré-treinado, [PREENCHER: épocas] épocas, imagem 640,
  semente fixa, sem espelhamento horizontal (letreiro espelhado não existe). Divisão 80/15/5.

[PRINT: 6 a 8 imagens do dataset sintético com as caixas (`python sintetico.py --amostra`)]

## 4. Resultados

| Modelo | mAP50 | mAP50-95 | Precisão | Revocação |
|---|---|---|---|---|
| Só sintético | [PREENCHER] | [PREENCHER] | [PREENCHER] | [PREENCHER] |
| Sintético + reais | [PREENCHER] | [PREENCHER] | [PREENCHER] | [PREENCHER] |

[PRINT: curvas do treino (`execucoes/letreiro/results.png`) e matriz de confusão]

**Ponta a ponta na maquete** (20 passagens de letreiro impresso):

| Detector | Linha certa confirmada | Linha errada confirmada | Tempo até confirmar |
|---|---|---|---|
| Só OCR | [PREENCHER]/20 | [PREENCHER] | [PREENCHER] s |
| YOLO + OCR | [PREENCHER]/20 | [PREENCHER] | [PREENCHER] s |

[PRINT: janela da câmera (`--janela`) com o letreiro marcado e a linha lida]

## 5. Decisões

- **Vocabulário restrito + votação** em vez de confiar no OCR cru: o letreiro de LED pisca e alterna
  textos, e o OCR troca letras. Restringir às linhas da parada transforma "leitura livre" em
  "escolher entre poucas opções", e a votação elimina leituras isoladas erradas.
- **Dados sintéticos** para começar sem rotular à mão e para cobrir variações raras (noite, ângulo,
  desfoque); as fotos reais medem o que importa: ônibus de verdade.
- **Processar no ponto (edge)** e publicar só texto: privacidade (sem vídeo de pessoas na nuvem) e
  pouca banda.
- **Rastreador entre detecções**: o OCR leva até ~1 s na CPU; o rastreador dá a posição a cada
  quadro para o braço seguir o ônibus suavemente.

## 6. Limitações e próximos passos

- Letreiros com reflexo forte do sol e ônibus muito de lado ainda falham; mais fotos reais nessas
  condições.
- Exportar o modelo para ONNX/TensorRT e rodar numa placa embarcada no lugar do notebook.
- Usar a previsão do Olho Vivo (qual ônibus deve chegar agora) como prior na votação.

## 7. Como testar

```bash
cd visao && pip install -r requirements.txt && python imprimir.py      # letreiros para imprimir
cd ../edge && .\iniciar.ps1                                            # Windows: webcam + janela
```

Detalhes: `visao/README.md` e `edge/README.md`.
