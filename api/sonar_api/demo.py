"""Modo demonstração: a jornada inteira com dados de exemplo em cerca de 2 minutos.

Usa as mesmas regras da operação real (servico.Sonar). Se um Sonar Ponto estiver
configurado com a parada "demo" e um Sonar Bordo com o prefixo 90001, o hardware
da maquete participa da demonstração de verdade.
"""

import asyncio

from starlette.concurrency import run_in_threadpool

from .olhovivo import Veiculo

PARADA_DEMO = "demo"
LINHA_CERTA, PREFIXO_CERTO, DESTINO_CERTO = "DEMO-10", "90001", "Terminal Exemplo"
LINHA_ERRADA, PREFIXO_ERRADO, DESTINO_ERRADO = "DEMO-20", "90002", "Centro (exemplo)"


def previsao_exemplo(minutos_certa: int, minutos_errada: int) -> list[Veiculo]:
    return sorted(
        [
            Veiculo(LINHA_CERTA, DESTINO_CERTO, PREFIXO_CERTO, minutos_certa, True),
            Veiculo(LINHA_ERRADA, DESTINO_ERRADO, PREFIXO_ERRADO, minutos_errada, True),
        ],
        key=lambda v: v.minutos,
    )


_ERRADA_PAROU = {"linha_lida": LINHA_ERRADA, "confianca": 0.92, "tempo_parado_s": 8.0, "parou": True}
_CERTA_PAROU = {"linha_lida": LINHA_CERTA, "confianca": 0.95, "tempo_parado_s": 14.0, "parou": True}
_CERTA_PASSOU = {"linha_lida": LINHA_CERTA, "confianca": 0.93, "tempo_parado_s": 0.6, "parou": False}

# (segundos desde o início, passo, dados)
ROTEIROS: dict[str, list[tuple[float, str, object]]] = {
    "embarque": [
        (3, "previsao", (6, 3)),
        (12, "previsao", (4, 2)),
        (35, "ciente", None),
        (45, "deteccao", _ERRADA_PAROU),
        (70, "deteccao", _CERTA_PAROU),
    ],
    "nao_parou": [
        (3, "previsao", (6, 3)),
        (12, "previsao", (4, 2)),
        (35, "ciente", None),
        (45, "deteccao", _ERRADA_PAROU),
        (70, "deteccao", _CERTA_PASSOU),
    ],
    # na maquete, o "ciente" vem do botão do Sonar Bordo e a detecção vem do Sonar Ponto
    "maquete": [
        (3, "previsao", (6, 3)),
        (12, "previsao", (4, 2)),
    ],
}

PREVISAO_INICIAL = previsao_exemplo(6, 3)


PREFIXOS = {LINHA_CERTA: PREFIXO_CERTO, LINHA_ERRADA: PREFIXO_ERRADO, "DEMO-30": "90003"}


def _prefixo(linha: str) -> str:
    return PREFIXOS.get(linha, "9" + "".join(c for c in linha if c.isdigit())[:4].ljust(4, "0"))


def _previsao_da_espera(parada, certa: str, outra: str | None, minutos_certa: int, minutos_outra: int) -> list[Veiculo]:
    veiculos = [Veiculo(certa, parada.destino(certa), _prefixo(certa), minutos_certa, True)]
    if outra:
        veiculos.append(Veiculo(outra, parada.destino(outra), _prefixo(outra), minutos_outra, True))
    return sorted(veiculos, key=lambda v: v.minutos)


async def executar(sonar, espera_id: str, cenario: str, velocidade: float) -> None:
    """Roda o roteiro na parada e na linha da própria espera (a maquete, ou um ponto da rede de demonstração).

    A "linha certa" é a que a pessoa espera; a "errada" é outra linha do mesmo ponto, se houver.
    """
    loop = asyncio.get_running_loop()
    inicio = loop.time()
    primeira = await run_in_threadpool(sonar.obter_espera, espera_id)
    parada_id, certa = primeira["parada_id"], primeira["linhas"][0]
    parada = sonar.paradas.obter(parada_id)
    outra = next((linha for linha in parada.codigos if linha != certa), None)
    for instante, passo, dados in ROTEIROS[cenario]:
        await asyncio.sleep(max(0.0, inicio + instante / velocidade - loop.time()))
        espera = await run_in_threadpool(sonar.obter_espera, espera_id)
        if espera["status"] != "aguardando":
            return
        if passo == "previsao":
            veiculos = _previsao_da_espera(parada, certa, outra, *dados)
            sonar.previsao_demo_por_parada[parada_id] = veiculos
            if parada_id == PARADA_DEMO:
                sonar.previsao_demo = veiculos
            await run_in_threadpool(sonar.processar_previsao, parada_id, veiculos, True)
        elif passo == "ciente":
            aviso = espera.get("aviso")
            if aviso and not aviso.get("ciente_em"):
                await run_in_threadpool(
                    sonar.registrar_ciente, aviso["prefixo"], {"espera_id": espera_id, "simulado": True}
                )
        elif passo == "deteccao":
            linha_lida = certa if dados["linha_lida"] == LINHA_CERTA else outra
            if linha_lida is None:
                continue  # ponto com uma linha só: não há "ônibus errado" para mostrar
            await run_in_threadpool(
                sonar.processar_deteccao, parada_id, {**dados, "linha_lida": linha_lida, "origem": "demo"}
            )
