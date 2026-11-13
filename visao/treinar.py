"""Treino reproduzível do detector de letreiro (YOLO, uma classe: letreiro).

    python treinar.py                                         # dataset sintético (gere antes com sintetico.py)
    python treinar.py --dados dados/sintetico/letreiros.yaml dados/roboflow/data.yaml   # sintético + fotos reais
    python treinar.py --rapido                                # 5 épocas, imagem 416: só para ver se roda

No fim, copia o melhor peso para ../edge/modelos/letreiro.pt (onde o serviço da câmera procura)
e imprime as métricas do conjunto de teste (mAP50, precisão, revocação) para o relatório.
Com GPU (Colab), 50 épocas em ~1500 imagens levam poucos minutos; na CPU, algumas horas.
"""

import argparse
import shutil
import tempfile
from pathlib import Path

PASTA = Path(__file__).resolve().parent
DESTINO_MODELO = PASTA.parent / "edge" / "modelos" / "letreiro.pt"


def _caminho_da_parte(yaml_arquivo: Path, dados: dict, parte: str) -> str | None:
    valor = dados.get(parte)
    if not valor:
        return None
    base = Path(dados["path"]) if dados.get("path") else yaml_arquivo.parent
    if not base.is_absolute():
        base = (yaml_arquivo.parent / base).resolve()
    candidato = (base / valor).resolve()
    if not candidato.exists() and str(valor).startswith("../"):
        candidato = (yaml_arquivo.parent / str(valor)[3:]).resolve()  # formato de exportação do Roboflow
    return candidato.as_posix()


def juntar(arquivos: list[Path]) -> Path:
    """Vários datasets (sintético + Roboflow) viram um só, com as listas de pastas de cada parte."""
    import yaml  # noqa: PLC0415 - vem com o ultralytics

    partes: dict[str, list[str]] = {"train": [], "val": [], "test": []}
    for arquivo in arquivos:
        dados = yaml.safe_load(arquivo.read_text(encoding="utf-8"))
        nomes = dados.get("names")
        nomes = list(nomes.values()) if isinstance(nomes, dict) else nomes
        if nomes and [n.lower() for n in nomes] != ["letreiro"]:
            raise SystemExit(f"{arquivo}: o dataset precisa ter uma classe só, 'letreiro' (tem {nomes})")
        for parte in partes:
            caminho = _caminho_da_parte(arquivo, dados, parte)
            if caminho and Path(caminho).is_dir():
                partes[parte].append(caminho)
            elif caminho:
                print(f"aviso: {caminho} não existe; ignorando ({arquivo.name}, {parte})")
    if not partes["train"] or not partes["val"]:
        raise SystemExit("nenhuma pasta de treino/validação encontrada nos datasets informados")
    juntado = Path(tempfile.mkdtemp()) / "juntado.yaml"
    juntado.write_text(yaml.safe_dump({**{k: v for k, v in partes.items() if v}, "names": {0: "letreiro"}}), encoding="utf-8")
    return juntado


def main() -> None:
    argumentos = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    argumentos.add_argument("--dados", nargs="+", default=[str(PASTA / "dados" / "sintetico" / "letreiros.yaml")])
    argumentos.add_argument("--epocas", type=int, default=50)
    argumentos.add_argument("--imagem", type=int, default=640)
    argumentos.add_argument("--base", default="yolo11n.pt", help="modelo pré-treinado de partida (o menor é o mais rápido)")
    argumentos.add_argument("--rapido", action="store_true")
    argumentos.add_argument("--nao-copiar", action="store_true", help="não copia o modelo para o edge/")
    opcoes = argumentos.parse_args()

    from ultralytics import YOLO  # noqa: PLC0415

    arquivos = [Path(a) for a in opcoes.dados]
    for arquivo in arquivos:
        if not arquivo.is_file():
            raise SystemExit(f"{arquivo} não existe. Gere o sintético antes: python sintetico.py --quantidade 1500")
    dados = juntar(arquivos)  # caminhos absolutos: funciona de qualquer pasta (e no Colab)
    epocas, imagem = (5, 416) if opcoes.rapido else (opcoes.epocas, opcoes.imagem)

    modelo = YOLO(opcoes.base)
    modelo.train(
        data=str(dados), epochs=epocas, imgsz=imagem, seed=42, deterministic=True,
        project=str(PASTA / "execucoes"), name="letreiro", exist_ok=True,
        fliplr=0.0,  # letreiro espelhado não existe (e confundiria o OCR)
    )
    melhor = PASTA / "execucoes" / "letreiro" / "weights" / "best.pt"
    metricas = YOLO(str(melhor)).val(data=str(dados), split="test" if "test" in dados.read_text() else "val")
    print("\nMétricas para o relatório:")
    print(f"  mAP50:     {metricas.box.map50:.3f}")
    print(f"  mAP50-95:  {metricas.box.map:.3f}")
    print(f"  precisão:  {metricas.box.mp:.3f}")
    print(f"  revocação: {metricas.box.mr:.3f}")
    print(f"  gráficos e matriz de confusão em {melhor.parent.parent}")
    if not opcoes.nao_copiar:
        DESTINO_MODELO.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(melhor, DESTINO_MODELO)
        print(f"  modelo copiado para {DESTINO_MODELO} (o serviço da câmera usa sozinho)")


if __name__ == "__main__":
    main()
