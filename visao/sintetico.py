"""Dataset sintético de letreiros de ônibus, já rotulado no formato YOLO.

Rotular foto por foto é o trabalho mais demorado da Visão. Este gerador desenha letreiros (estilo LED
ou impresso, âmbar/branco/verde, com e sem a frente do ônibus), aplica perspectiva, desfoque, ruído e
luz, e grava a caixa exata de cada letreiro. Serve para:

- treinar um primeiro modelo sem rotular nada (ótimo para os letreiros impressos da maquete);
- completar um dataset pequeno de fotos reais (junte os dois no treino; veja o README).

    python sintetico.py --quantidade 1500                 # dados/sintetico/ + letreiros.yaml
    python sintetico.py --quantidade 1500 --fundos fotos/ # usa suas fotos de rua como fundo
    python sintetico.py --amostra                         # 12 imagens com a caixa desenhada, para conferir

Imagens com rosto ou placa de carro não entram aqui: os fundos são sintéticos ou fotos suas
(sem ônibus, de preferência sem pessoas).
"""

import argparse
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

TAMANHO = 640
CORES_LED = [(255, 176, 0), (255, 200, 40), (235, 235, 235), (120, 255, 120)]
CORES_ONIBUS = [(235, 235, 230), (200, 30, 30), (20, 80, 170), (30, 140, 70), (240, 190, 20), (90, 90, 95)]
DESTINOS = [
    "TERM. LAPA", "TERM. PINHEIROS", "PCA. DA SE", "METRO ITAQUERA", "TERM. PENHA", "SANTANA",
    "VILA MARIANA", "TERM. CAPELINHA", "JD. ANGELA", "METRO TUCURUVI", "TERM. SAO MATEUS",
    "BUTANTA", "TERM. STO AMARO", "CENTRO", "TERMINAL EXEMPLO", "PQ. D. PEDRO II", "BARRA FUNDA",
]
LINHAS_FIXAS = ["DEMO-10", "DEMO-20", "8000-10", "875A-10"]
FONTES = [
    "DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]
_cache_fontes: dict[int, ImageFont.ImageFont] = {}


def fonte(tamanho: int) -> ImageFont.ImageFont:
    if tamanho not in _cache_fontes:
        for nome in FONTES:
            try:
                _cache_fontes[tamanho] = ImageFont.truetype(nome, tamanho)
                break
            except OSError:
                continue
        else:
            _cache_fontes[tamanho] = ImageFont.load_default(size=tamanho)
    return _cache_fontes[tamanho]


def linha_aleatoria(rng: random.Random) -> str:
    if rng.random() < 0.35:
        return rng.choice(LINHAS_FIXAS)
    base = f"{rng.randint(1000, 9999)}" if rng.random() < 0.8 else f"{rng.randint(100, 999)}{rng.choice('ACHMNP')}"
    return f"{base}-{rng.choice(['10', '10', '10', '21', '31', '41'])}"


# ------------------------------------------------------------------------------------- desenho


def _mascara_texto(partes: list[tuple[str, int]], altura: int, margem: int) -> Image.Image:
    """Máscara (L) com os textos lado a lado, centralizados na vertical."""
    larguras = [fonte(t).getbbox(texto)[2] for texto, t in partes]
    espaco = altura // 3
    largura = sum(larguras) + espaco * (len(partes) - 1) + 2 * margem
    mascara = Image.new("L", (max(largura, altura), altura), 0)
    desenho = ImageDraw.Draw(mascara)
    x = margem
    for (texto, tamanho), w in zip(partes, larguras):
        caixa = fonte(tamanho).getbbox(texto)
        y = (altura - (caixa[3] - caixa[1])) // 2 - caixa[1]
        desenho.text((x, y), texto, fill=255, font=fonte(tamanho))
        x += w + espaco
    return mascara


def _efeito_led(mascara: Image.Image, passo: int) -> Image.Image:
    """Transforma a máscara em pontos de LED (matriz de pontos)."""
    w, h = mascara.size
    pequena = np.asarray(mascara.resize((max(1, w // passo), max(1, h // passo)), Image.BILINEAR)) > 90
    yy, xx = np.mgrid[0:passo, 0:passo]
    raio = passo * 0.42
    ponto = (((xx - (passo - 1) / 2) ** 2 + (yy - (passo - 1) / 2) ** 2) <= raio**2).astype(np.uint8) * 255
    pontos = np.kron(pequena.astype(np.uint8), ponto)
    saida = np.zeros((h, w), np.uint8)
    ph, pw = min(h, pontos.shape[0]), min(w, pontos.shape[1])
    saida[:ph, :pw] = pontos[:ph, :pw]
    return Image.fromarray(saida)


def desenhar_letreiro(
    linha: str,
    destino: str,
    rng: random.Random,
    estilo: str | None = None,
    disposicao: str | None = None,
    cor: tuple[int, int, int] | None = None,
) -> Image.Image:
    """Letreiro RGBA: painel escuro com o texto aceso."""
    estilo = estilo or rng.choice(["led", "led", "impresso"])
    altura = rng.choice([90, 110, 130])
    if disposicao is None:
        sorteio = rng.random()
        disposicao = "ambos" if sorteio < 0.6 else "linha" if sorteio < 0.8 else "destino"
    if disposicao == "ambos":
        partes = [(linha, int(altura * 0.62)), (destino, int(altura * 0.45))]
    elif disposicao == "linha":
        partes = [(linha, int(altura * 0.7))]
    else:
        partes = [(destino, int(altura * 0.5))]  # o letreiro alterna: às vezes só o destino aparece
    mascara = _mascara_texto(partes, altura, margem=altura // 4)
    cor = cor or rng.choice(CORES_LED)
    if estilo == "led":
        mascara = _efeito_led(mascara, passo=rng.choice([4, 5, 6]))
    painel = Image.new("RGBA", mascara.size, (*(rng.randint(5, 30) for _ in range(3)), 255))
    acesa = Image.new("RGBA", mascara.size, (*cor, 255))
    if estilo == "led":
        brilho = mascara.filter(ImageFilter.GaussianBlur(3)).point(lambda v: int(v * 0.6))
        painel.paste(acesa, (0, 0), brilho)
    painel.paste(acesa, (0, 0), mascara)
    moldura = ImageDraw.Draw(painel)
    moldura.rectangle([0, 0, painel.width - 1, painel.height - 1], outline=(60, 60, 60, 255), width=max(2, altura // 25))
    return painel


def desenhar_frente(letreiro: Image.Image, rng: random.Random) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Frente de ônibus simplificada com o letreiro no alto. Devolve a imagem e a caixa do letreiro."""
    lw, lh = letreiro.size
    largura, altura = int(lw * rng.uniform(1.15, 1.4)), int(lw * rng.uniform(0.9, 1.2))
    cor = rng.choice(CORES_ONIBUS)
    frente = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(frente)
    desenho.rounded_rectangle([0, 0, largura - 1, altura - 1], radius=largura // 12, fill=(*cor, 255))
    x0, y0 = (largura - lw) // 2, int(altura * 0.05)
    para_brisa = [int(largura * 0.06), y0 + lh + 8, int(largura * 0.94), int(altura * 0.62)]
    desenho.rounded_rectangle(para_brisa, radius=largura // 30, fill=(25, 35, 45, 255))
    for lado in (0.12, 0.78):
        desenho.ellipse(
            [int(largura * lado), int(altura * 0.78), int(largura * (lado + 0.1)), int(altura * 0.86)],
            fill=(250, 250, 220, 255),
        )
    frente.paste(letreiro, (x0, y0), letreiro)
    return frente, (x0, y0, x0 + lw, y0 + lh)


def fundo(rng: random.Random, fotos: list[Path]) -> Image.Image:
    if fotos and rng.random() < 0.8:
        foto = Image.open(rng.choice(fotos)).convert("RGB")
        lado = min(foto.size)
        escala = rng.uniform(0.5, 1.0)
        corte = int(lado * escala)
        x, y = rng.randint(0, foto.width - corte), rng.randint(0, foto.height - corte)
        return foto.crop((x, y, x + corte, y + corte)).resize((TAMANHO, TAMANHO))
    topo = np.array([rng.randint(60, 220) for _ in range(3)], float)
    base = np.array([rng.randint(20, 160) for _ in range(3)], float)
    t = np.linspace(0, 1, TAMANHO)[:, None, None]
    imagem = Image.fromarray(((1 - t) * topo + t * base).repeat(TAMANHO, axis=1).astype(np.uint8))
    desenho = ImageDraw.Draw(imagem)
    for _ in range(rng.randint(4, 14)):  # prédios, postes, placas, carros: formas que não são letreiro
        x1, y1 = rng.randint(-50, TAMANHO), rng.randint(-50, TAMANHO)
        x2, y2 = x1 + rng.randint(20, 260), y1 + rng.randint(20, 260)
        cor = tuple(rng.randint(0, 255) for _ in range(3))
        if rng.random() < 0.5:
            desenho.rectangle([x1, y1, x2, y2], fill=cor)
        else:
            desenho.line([x1, y1, x2, y2], fill=cor, width=rng.randint(2, 12))
    if rng.random() < 0.6:  # texto que NÃO é letreiro (loja, placa de rua): o modelo aprende a ignorar
        texto = rng.choice(["FARMACIA", "PADARIA", "AV. PAULISTA", "R. AUGUSTA", "PARE", "LOJA 24H"])
        desenho.text((rng.randint(0, 500), rng.randint(0, 600)), texto, font=fonte(rng.randint(18, 40)),
                     fill=tuple(rng.randint(0, 255) for _ in range(3)))
    return imagem


# ------------------------------------------------------------------------------------- perspectiva


def homografia(origem: np.ndarray, destino: np.ndarray) -> np.ndarray:
    """Matriz 3x3 que leva os 4 pontos de origem nos 4 de destino."""
    linhas = []
    for (x, y), (u, v) in zip(origem, destino):
        linhas.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        linhas.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    h = np.linalg.solve(np.array(linhas, float), destino.reshape(-1).astype(float))
    return np.append(h, 1).reshape(3, 3)


def aplicar(matriz: np.ndarray, pontos: np.ndarray) -> np.ndarray:
    p = np.hstack([pontos, np.ones((len(pontos), 1))]) @ matriz.T
    return p[:, :2] / p[:, 2:3]


def colar_com_perspectiva(
    tela: Image.Image, objeto: Image.Image, caixa_letreiro: tuple[int, int, int, int], rng: random.Random
) -> tuple[float, float, float, float]:
    """Cola o objeto (frente/letreiro) com perspectiva aleatória. Devolve a caixa do letreiro na tela."""
    ow, oh = objeto.size
    largura_letreiro = rng.uniform(0.15, 0.7) * TAMANHO
    escala = largura_letreiro / (caixa_letreiro[2] - caixa_letreiro[0])
    w, h = ow * escala, oh * escala
    if w > TAMANHO * 0.95 or h > TAMANHO * 0.95:
        fator = min(TAMANHO * 0.95 / w, TAMANHO * 0.95 / h)
        w, h = w * fator, h * fator
    x0, y0 = rng.uniform(0, TAMANHO - w), rng.uniform(0, TAMANHO - h)
    tremor = 0.12
    destino = np.array(
        [
            [x0 + rng.uniform(-tremor, tremor) * w, y0 + rng.uniform(-tremor, tremor) * h],
            [x0 + w + rng.uniform(-tremor, tremor) * w, y0 + rng.uniform(-tremor, tremor) * h],
            [x0 + w + rng.uniform(-tremor, tremor) * w, y0 + h + rng.uniform(-tremor, tremor) * h],
            [x0 + rng.uniform(-tremor, tremor) * w, y0 + h + rng.uniform(-tremor, tremor) * h],
        ]
    ).clip(0, TAMANHO - 1)
    origem = np.array([[0, 0], [ow, 0], [ow, oh], [0, oh]], float)
    ida = homografia(origem, destino)
    volta = np.linalg.inv(ida)
    volta /= volta[2, 2]
    torto = objeto.transform((TAMANHO, TAMANHO), Image.Transform.PERSPECTIVE, volta.reshape(-1)[:8], Image.BICUBIC)
    tela.paste(torto, (0, 0), torto)
    lx1, ly1, lx2, ly2 = caixa_letreiro
    cantos = aplicar(ida, np.array([[lx1, ly1], [lx2, ly1], [lx2, ly2], [lx1, ly2]], float)).clip(0, TAMANHO)
    return cantos[:, 0].min(), cantos[:, 1].min(), cantos[:, 0].max(), cantos[:, 1].max()


def degradar(imagem: Image.Image, rng: random.Random) -> Image.Image:
    imagem = ImageEnhance.Brightness(imagem).enhance(rng.uniform(0.5, 1.4))
    imagem = ImageEnhance.Contrast(imagem).enhance(rng.uniform(0.6, 1.3))
    if rng.random() < 0.6:
        imagem = imagem.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.8)))
    if rng.random() < 0.3:  # borrão de movimento (ônibus chegando)
        imagem = imagem.filter(ImageFilter.BoxBlur(rng.uniform(0.5, 2)))
    ruido = np.random.default_rng(rng.randint(0, 2**31)).normal(0, rng.uniform(2, 12), (TAMANHO, TAMANHO, 3))
    return Image.fromarray(np.clip(np.asarray(imagem, float) + ruido, 0, 255).astype(np.uint8))


# ------------------------------------------------------------------------------------- dataset


def gerar_exemplo(rng: random.Random, fotos: list[Path]) -> tuple[Image.Image, list[tuple[float, ...]]]:
    tela = fundo(rng, fotos).convert("RGBA")
    caixas = []
    if rng.random() > 0.1:  # ~10% sem letreiro: ensina o modelo a não ver letreiro em tudo
        for _ in range(1 if rng.random() < 0.85 else 2):
            letreiro = desenhar_letreiro(linha_aleatoria(rng), rng.choice(DESTINOS), rng)
            if rng.random() < 0.6:
                objeto, caixa = desenhar_frente(letreiro, rng)
            else:
                objeto, caixa = letreiro, (0, 0, *letreiro.size)
            x1, y1, x2, y2 = colar_com_perspectiva(tela, objeto, caixa, rng)
            if x2 - x1 > 8 and y2 - y1 > 4:
                caixas.append(((x1 + x2) / 2 / TAMANHO, (y1 + y2) / 2 / TAMANHO, (x2 - x1) / TAMANHO, (y2 - y1) / TAMANHO))
    return degradar(tela.convert("RGB"), rng), caixas


def gerar_dataset(saida: Path, quantidade: int, semente: int = 42, fotos: list[Path] | None = None) -> Path:
    rng = random.Random(semente)
    fotos = fotos or []
    for i in range(quantidade):
        parte = "train" if i % 20 < 16 else "val" if i % 20 < 19 else "test"
        imagem, caixas = gerar_exemplo(rng, fotos)
        (saida / "images" / parte).mkdir(parents=True, exist_ok=True)
        (saida / "labels" / parte).mkdir(parents=True, exist_ok=True)
        nome = f"sint_{i:05d}"
        imagem.save(saida / "images" / parte / f"{nome}.jpg", quality=rng.randint(45, 95))
        rotulos = "\n".join(f"0 {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}" for cx, cy, w, h in caixas)
        (saida / "labels" / parte / f"{nome}.txt").write_text(rotulos + ("\n" if rotulos else ""), encoding="utf-8")
    yaml = saida / "letreiros.yaml"
    yaml.write_text(
        "# gerado por sintetico.py\n"
        f"path: {saida.resolve().as_posix()}\n"
        "train: images/train\nval: images/val\ntest: images/test\nnames:\n  0: letreiro\n",
        encoding="utf-8",
    )
    return yaml


def amostra(saida: Path, semente: int = 7) -> None:
    """Gera 12 exemplos com a caixa desenhada, para conferir o rótulo a olho."""
    rng = random.Random(semente)
    saida.mkdir(parents=True, exist_ok=True)
    for i in range(12):
        imagem, caixas = gerar_exemplo(rng, [])
        desenho = ImageDraw.Draw(imagem)
        for cx, cy, w, h in caixas:
            desenho.rectangle(
                [(cx - w / 2) * TAMANHO, (cy - h / 2) * TAMANHO, (cx + w / 2) * TAMANHO, (cy + h / 2) * TAMANHO],
                outline=(0, 255, 0), width=3,
            )
        imagem.save(saida / f"amostra_{i:02d}.jpg", quality=90)


def main() -> None:
    argumentos = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    argumentos.add_argument("--quantidade", type=int, default=1500)
    argumentos.add_argument("--saida", default="dados/sintetico")
    argumentos.add_argument("--fundos", help="pasta com fotos (jpg/png) para usar de fundo")
    argumentos.add_argument("--semente", type=int, default=42)
    argumentos.add_argument("--amostra", action="store_true", help="só 12 imagens com a caixa desenhada")
    opcoes = argumentos.parse_args()
    if opcoes.amostra:
        amostra(Path(opcoes.saida) / "amostra")
        print(f"amostras em {Path(opcoes.saida) / 'amostra'}")
        return
    fotos = []
    if opcoes.fundos:
        fotos = [p for p in Path(opcoes.fundos).rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"}]
        print(f"{len(fotos)} fotos de fundo")
    yaml = gerar_dataset(Path(opcoes.saida), opcoes.quantidade, opcoes.semente, fotos)
    print(f"{opcoes.quantidade} imagens geradas. Treine com: python treinar.py --dados {yaml}")


if __name__ == "__main__":
    main()
