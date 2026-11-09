"""Treino reproduzível do detector de letreiro."""

import argparse


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dados", default="dados/letreiros.yaml")
    p.add_argument("--epocas", type=int, default=50)
    p.add_argument("--imagem", type=int, default=640)
    p.add_argument("--base", default="yolo11n.pt")
    a = p.parse_args()

    from ultralytics import YOLO

    modelo = YOLO(a.base)
    modelo.train(data=a.dados, epochs=a.epocas, imgsz=a.imagem, seed=42, project="execucoes", name="letreiro")
    print(modelo.val(split="test"))


if __name__ == "__main__":
    main()
