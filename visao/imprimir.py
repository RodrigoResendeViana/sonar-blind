"""Letreiros para imprimir e colar no "ônibus" da maquete.

    python imprimir.py                                  # DEMO-10 e DEMO-20 (as linhas da demonstração)
    python imprimir.py --letreiro "8000-10" "TERM. LAPA" --letreiro "875A-10" "PERDIZES"
    python imprimir.py --led                            # estilo matriz de LED (mais real, mais difícil para o OCR)

Gera um PNG por letreiro e um PDF com todos (A4 deitado, uma página por letreiro) em impressao/.
Imprima em cores, sem "ajustar à página" desligado: o letreiro ocupa a largura da folha.
"""

import argparse
import random
from pathlib import Path

from PIL import Image, ImageDraw

from sintetico import desenhar_letreiro, fonte

A4_DEITADO = (3508 // 2, 2480 // 2)  # 150 dpi
PADRAO = [("DEMO-10", "TERMINAL EXEMPLO"), ("DEMO-20", "CENTRO")]


def pagina(linha: str, destino: str, led: bool) -> Image.Image:
    folha = Image.new("RGB", A4_DEITADO, "white")
    letreiro = desenhar_letreiro(
        linha, destino, random.Random(0), estilo="led" if led else "impresso", disposicao="ambos", cor=(255, 176, 0)
    )
    largura = int(A4_DEITADO[0] * 0.9)
    altura = int(letreiro.height * largura / letreiro.width)
    letreiro = letreiro.resize((largura, altura), Image.NEAREST if led else Image.LANCZOS)
    x, y = (A4_DEITADO[0] - largura) // 2, (A4_DEITADO[1] - altura) // 3
    folha.paste(letreiro, (x, y), letreiro)
    desenho = ImageDraw.Draw(folha)
    for dx, dy in ((x, y), (x + largura, y), (x, y + altura), (x + largura, y + altura)):  # marcas de corte
        desenho.line([dx - 30, dy, dx + 30, dy], fill="gray", width=2)
        desenho.line([dx, dy - 30, dx, dy + 30], fill="gray", width=2)
    desenho.text(
        (x, y + altura + 60),
        f"Sonar: {linha} {destino}. Recorte nas marcas e cole na frente do ônibus.",
        fill="gray",
        font=fonte(28),
    )
    return folha


def main() -> None:
    argumentos = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    argumentos.add_argument("--letreiro", nargs=2, action="append", metavar=("LINHA", "DESTINO"))
    argumentos.add_argument("--led", action="store_true")
    argumentos.add_argument("--saida", default="impressao")
    opcoes = argumentos.parse_args()
    saida = Path(opcoes.saida)
    saida.mkdir(parents=True, exist_ok=True)
    paginas = []
    for linha, destino in opcoes.letreiro or PADRAO:
        folha = pagina(linha.upper(), destino.upper(), opcoes.led)
        folha.save(saida / f"letreiro_{linha.upper()}.png")
        paginas.append(folha)
    paginas[0].save(saida / "letreiros.pdf", save_all=True, append_images=paginas[1:], resolution=150)
    print(f"{len(paginas)} letreiro(s) em {saida.resolve()} (PNG + letreiros.pdf)")


if __name__ == "__main__":
    main()
