# Visão computacional (equipe de Visão)

Acha o **letreiro do ônibus** no quadro da câmera e lê a linha. O serviço da câmera
([`edge/`](../edge/README.md)) roda no notebook do ponto e publica só o texto lido (e a posição do
letreiro, para o braço do Maker Lab). Nenhuma imagem sai do notebook.

## Três níveis, do mais simples ao mais completo

| Nível | Como acha o letreiro | Precisa treinar? | Quando usar |
|---|---|---|---|
| 1. Só OCR | EasyOCR acha e lê todos os textos do quadro | não | já funciona hoje, com os letreiros impressos da maquete |
| 2. YOLO sintético | modelo treinado só com letreiros gerados por `sintetico.py` | sim, sem rotular nada | rápido de treinar; bom para a maquete |
| 3. YOLO sintético + fotos reais | o mesmo, completado com fotos reais rotuladas no Roboflow | sim | a entrega da matéria (métricas em ônibus de verdade) |

O serviço da câmera escolhe sozinho: se `edge/modelos/letreiro.pt` existir, usa o YOLO (nível 2/3);
senão, só o OCR (nível 1). Em qualquer nível, o texto lido passa pelo vocabulário restrito da parada
(só as linhas que passam ali) e por uma votação de 3 quadros seguidos (`edge/sonar_camera/votacao.py`).

Entre uma detecção e outra (o OCR leva até ~1 s na CPU), um rastreador por correlação
(`edge/sonar_camera/rastreador.py`) segue o letreiro quadro a quadro: é o que deixa o braço suave.

## Letreiros para a maquete

```bash
cd visao
pip install -r requirements.txt
python imprimir.py                      # DEMO-10 e DEMO-20, as linhas da demonstração
python imprimir.py --letreiro "8000-10" "TERM. LAPA"
```

Gera `impressao/letreiros.pdf` (A4 deitado, uma página por letreiro). Imprima em cores e cole na
frente do "ônibus" de papelão.

## Dataset sintético (sem rotular nada)

```bash
python sintetico.py --amostra           # 12 exemplos com a caixa desenhada: confira se está certo
python sintetico.py --quantidade 1500   # dados/sintetico/ (imagens + rótulos YOLO + letreiros.yaml)
python sintetico.py --quantidade 1500 --fundos minhas_fotos/   # fotos de rua suas como fundo
```

O gerador desenha letreiros LED e impressos (âmbar, branco, verde), com e sem a frente do ônibus,
com perspectiva, desfoque, ruído, luz e textos que não são letreiro (loja, placa de rua), e grava a
caixa exata de cada letreiro. Cerca de 10% das imagens não têm letreiro, para o modelo não ver
letreiro em tudo.

## Fotos reais (para a entrega)

1. Juntar 150 a 300 fotos de ônibus com o letreiro visível (rua, vídeos, sites de transporte), de
   dia e de noite, de frente e de lado.
2. **Borrar rostos e placas de carro antes de subir** (LGPD); não usar fotos de pessoas identificáveis.
3. No Roboflow: projeto de *Object Detection*, classe única **`letreiro`**, caixa só no painel do
   letreiro (não no ônibus inteiro). Exportar em **YOLOv8/YOLO11** e descompactar em `dados/roboflow/`.

## Treinar

No Colab (GPU grátis): Ambiente de execução → Alterar o tipo → T4 GPU, e então:

```bash
!git clone https://github.com/RodrigoResendeViana/sonar-blind.git
%cd sonar-blind/visao
!pip install -q -r requirements-treino.txt
!python sintetico.py --quantidade 1500
!python treinar.py                                                   # só sintético
!python treinar.py --dados dados/sintetico/letreiros.yaml dados/roboflow/data.yaml   # com as fotos reais
```

No fim, `treinar.py` imprime mAP50, mAP50-95, precisão e revocação do conjunto de teste e copia o
melhor modelo para `edge/modelos/letreiro.pt`. No Colab, baixe esse arquivo e coloque na mesma pasta
no notebook do ponto. Os gráficos do treino e a matriz de confusão ficam em `execucoes/letreiro/`.

O modelo (`*.pt`) e os datasets não vão para o Git (`.gitignore`): o `.pt` vai como anexo de uma
*release* do GitHub, se precisar compartilhar.

## Testar na câmera

```bash
cd edge
python -m sonar_camera --parada demo --linhas DEMO-10,DEMO-20 --modo webcam --janela --mirar-sempre
```

A janela mostra os textos lidos (laranja) e o letreiro que está sendo seguido (verde). Mexa o
letreiro impresso na frente da câmera.

## Medir (para o relatório)

- **Detector**: mAP50, precisão e revocação do teste (saída do `treinar.py`), comparando sintético
  só vs. sintético + reais.
- **Ponta a ponta**: em 20 passagens de letreiro impresso na maquete, quantas vezes a linha certa
  foi confirmada e em quanto tempo; e quantas vezes uma linha errada foi confirmada (deve ser zero:
  é o que o vocabulário restrito e a votação garantem).
- **Comparar os níveis**: só OCR vs. YOLO + OCR (acerto e tempo por quadro).

Testes do gerador: `pip install -r requirements-dev.txt && pytest`.
