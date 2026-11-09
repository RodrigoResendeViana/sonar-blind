# Visão computacional (equipe de Visão)

Treina o modelo YOLO que acha o **letreiro do ônibus** no quadro da câmera. O serviço da
câmera ([`edge/`](../edge/README.md)) recorta o letreiro, roda o OCR e publica só o texto.

## Entrega esperada

- `dados/letreiros.yaml`: configuração do dataset no formato Ultralytics (classe `letreiro`).
- Imagens e rótulos **fora do Git** (ficam no Drive/Roboflow da equipe; `dados/*/` está no
  `.gitignore`). Nada de rosto ou placa legível: recortar ou borrar antes de rotular (LGPD).
- `treinar.py`: treino reproduzível (semente, época, tamanho da imagem).
- Métricas no README: mAP50, precisão e revocação no conjunto de teste, e a taxa de acerto da
  linha lida ponta a ponta (YOLO + OCR + votação) em vídeos de ponto.
- O modelo final `letreiro.pt` vai como artefato de release, não no Git; o `edge` lê de
  `edge/modelos/letreiro.pt`.

## Treinar

```bash
cd visao
pip install ultralytics==8.3.*
python treinar.py --dados dados/letreiros.yaml --epocas 50
```

## Testar no serviço da câmera

```bash
cd edge
pip install -r requirements-visao.txt
python -m sonar_camera --parada demo --linhas DEMO-10,DEMO-20 --modo webcam --modelo modelos/letreiro.pt
```
