import random

import numpy as np

import imprimir
import sintetico


def test_dataset_rotulado_no_formato_yolo(tmp_path):
    yaml = sintetico.gerar_dataset(tmp_path / "ds", quantidade=20, semente=3)
    imagens = sorted((tmp_path / "ds" / "images").rglob("*.jpg"))
    rotulos = sorted((tmp_path / "ds" / "labels").rglob("*.txt"))
    assert len(imagens) == len(rotulos) == 20
    assert {p.parent.name for p in imagens} == {"train", "val", "test"}
    caixas = 0
    for rotulo in rotulos:
        for linha in rotulo.read_text().splitlines():
            classe, *valores = linha.split()
            assert classe == "0"
            cx, cy, w, h = map(float, valores)
            assert 0 < w <= 1 and 0 < h <= 1
            assert 0 <= cx - w / 2 + 1e-6 and cx + w / 2 <= 1 + 1e-6
            caixas += 1
    assert caixas >= 15
    texto = yaml.read_text()
    assert "train: images/train" in texto and "0: letreiro" in texto


def test_homografia_leva_os_cantos_no_lugar():
    origem = np.array([[0, 0], [100, 0], [100, 40], [0, 40]], float)
    destino = np.array([[10, 12], [120, 5], [118, 60], [8, 50]], float)
    matriz = sintetico.homografia(origem, destino)
    assert np.allclose(sintetico.aplicar(matriz, origem), destino)


def test_caixa_do_letreiro_cobre_o_texto_aceso():
    """A caixa gravada precisa coincidir com onde o letreiro foi parar na imagem."""
    rng = random.Random(11)
    tela = sintetico.Image.new("RGBA", (sintetico.TAMANHO, sintetico.TAMANHO), (0, 0, 255, 255))
    letreiro = sintetico.desenhar_letreiro("DEMO-10", "CENTRO", rng, estilo="impresso", disposicao="ambos")
    x1, y1, x2, y2 = sintetico.colar_com_perspectiva(tela, letreiro, (0, 0, *letreiro.size), rng)
    pixels = np.asarray(tela.convert("RGB")).astype(int)
    fora_do_azul = np.argwhere((pixels[:, :, 2] < 200) | (pixels[:, :, 0] > 50))
    ys, xs = fora_do_azul[:, 0], fora_do_azul[:, 1]
    assert abs(xs.min() - x1) <= 3 and abs(xs.max() - x2) <= 3
    assert abs(ys.min() - y1) <= 3 and abs(ys.max() - y2) <= 3


def test_letreiros_para_imprimir(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["imprimir.py", "--saida", str(tmp_path)])
    imprimir.main()
    assert (tmp_path / "letreiro_DEMO-10.png").exists()
    assert (tmp_path / "letreiros.pdf").read_bytes().startswith(b"%PDF")


def test_treino_junta_o_sintetico_com_as_fotos_reais(tmp_path):
    import yaml

    import treinar

    sintetico_yaml = sintetico.gerar_dataset(tmp_path / "sint", quantidade=20, semente=5)
    reais = tmp_path / "roboflow"
    for parte in ("train", "valid"):
        (reais / parte / "images").mkdir(parents=True)
    (reais / "data.yaml").write_text("train: ../train/images\nval: ../valid/images\nnc: 1\nnames: ['letreiro']\n")
    juntado = yaml.safe_load(treinar.juntar([sintetico_yaml, reais / "data.yaml"]).read_text())
    assert juntado["train"] == [(tmp_path / "sint/images/train").as_posix(), (reais / "train/images").as_posix()]
    assert len(juntado["val"]) == 2
    assert juntado["names"] == {0: "letreiro"}
