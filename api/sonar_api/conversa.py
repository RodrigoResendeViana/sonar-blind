"""Conversa por voz: o passageiro diz para onde vai e o Sonar conduz a viagem inteira.

    "quero ir para o hospital"
      → plano (até uma baldeação) com a previsão do primeiro ônibus → "Quer ir? Diga sim."
      → vá até o ponto; ao chegar (GPS a ~40 m, ou "cheguei"), o Sonar avisa o ponto:
        LED para o motorista, bip para achar o poste, câmera ligada, Sonar Bordo avisado
      → a câmera diz "não é o seu" / "é o seu"; "embarquei"
      → no ônibus, o GPS avisa quando descer (na demonstração, a viagem é simulada)
      → baldeação: o Sonar já avisa o próximo ponto; no fim, "você chegou"
    Se o ônibus passa direto: "quero reclamar" → o robô de RPA registra e devolve o protocolo.

O estado fica na memória da API (uma sessão por aparelho, some depois de algumas horas).
A localização serve só para o plano e para os avisos; não é gravada.
O entendimento das frases é por regras (rápido e previsível); o que as regras não entendem,
no meio da espera, vai para o agente de IA generativa.
"""

import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass, field

from starlette.concurrency import run_in_threadpool

from . import demo
from .ia import perguntar as perguntar_ia
from .metricas import VIAGENS_PLANEJADAS
from .olhovivo import OlhoVivoIndisponivel
from .paradas import Linha, Parada, distancia_m, normalizar_linha
from .planejador import Plano, Trecho, descrever, metros_falados, paradas_faladas, planejar, ponto_falado
from .rede import PontoRede, Rede, normalizar, termos
from .servico import Conflito, NaoEncontrado

log = logging.getLogger("sonar.conversa")

RAIO_CHEGOU_M = 40  # GPS: perto assim do ponto, o Sonar avisa o ponto sozinho
RAIO_PREPARAR_M = 450  # no ônibus: "prepare-se para descer"
RAIO_DESCER_M = 70
DEMO_PREPARAR_S, DEMO_DESCER_S = 15, 30  # viagem simulada (divididos pela velocidade da demonstração)
SESSAO_HORAS = 6

SAUDACAO = "Olá, eu sou o Sonar. Toque na tela e diga para onde você quer ir."
AJUDA = (
    "Você pode dizer: quero ir para, e o destino. No ponto: cheguei, quanto falta, apita, embarquei. "
    "Se o ônibus não parar: quero reclamar. No ônibus: desci. E a qualquer hora: repete, ou cancelar."
)

INTENCOES = [
    ("ajuda", r"\b(ajuda|socorro|o que (eu )?posso (falar|dizer)|como funciona|comandos)\b"),
    ("cancelar", r"\b(cancela|cancelar|desisto|desisti|esquece|recomecar|comecar de novo|parar tudo)\b"),
    ("esperar_de_novo", r"\b(esperar de novo|espera de novo|esperar o proximo|esperar outro)\b"),
    ("repetir", r"\b(repete|repetir|repita|fala de novo|nao entendi|o que voce disse)\b"),
    ("embarquei", r"\b(embarquei|entrei|subi|ja estou no onibus|to no onibus|estou no onibus)\b"),
    ("desci", r"\b(desci|ja desci|sai do onibus|saltei)\b"),
    ("reclamar", r"\b(reclamar|reclamacao|denunciar|denuncia|nao parou|nem parou|passou direto)\b"),
    ("cheguei", r"\b(cheguei|to no ponto|estou no ponto|ja estou no ponto|conecta|conectar|avisa o ponto|avise o ponto|chama o ponto)\b"),
    ("localizar", r"\b(onde fica o ponto|onde esta o ponto|cade o ponto|apita|apitar|bipa|bip|onde fica o poste|achar o poste)\b"),
    ("quanto_falta", r"\b(quanto falta|quanto tempo|quando chega|que horas chega|ta chegando|esta chegando|vai demorar|demora)\b"),
    ("proximo_passo", r"\b(e agora|o que (eu )?faco|proximo passo|onde (eu )?desco)\b"),
    ("outra_opcao", r"\b(outra opcao|outro caminho|outra rota|tem outro|outra forma)\b"),
    ("sim", r"^(sim|isso|pode|pode ser|ok|okay|claro|confirmo|confirma|bora|vamos|quero|beleza|certo|correto|aham|uhum|exato|positivo|com certeza|manda)\b"),
    ("nao", r"^(nao|negativo|errado|nada)\b"),
]
_INTENCOES = [(nome, re.compile(padrao)) for nome, padrao in INTENCOES]
_DESTINO_VERBO = re.compile(
    r"\b(?:ir|chegar|voltar|leva|leve|levar|chego|vou|pego|tomo|indo)\b"
    r"(?: (?:ate|para|pra|pro|ao|aos|a|as|no|na|nos|nas|em|o|os))+ (?P<destino>.+)$"
)
_DESTINO_CURTO = re.compile(r"^(?:destino|para|pra|pro|ate)(?: (?:o|a|os|as))? (?P<destino>.+)$")
_PALAVRA_DEMO = re.compile(r"\b(exemplo|demonstracao|maquete)\b")


_PEDIDO_DE_DESTINO = re.compile(r"^(quero|queria|preciso|me leva|me leve|leva|vou|mudar|mude|novo destino|outro destino)\b")
_ENCHIMENTO = {
    "quero", "queria", "preciso", "vou", "ir", "para", "pra", "pro", "o", "a", "os", "as", "ao", "no", "na", "me",
    "leva", "leve", "eu", "gostaria", "de", "ate", "em", "sim", "nao", "agora", "por", "favor",
}


def entender(texto: str) -> tuple[str | None, str | None, bool]:
    """(intenção, destino, pedido_explicito) de uma frase.

    O destino sai com verbo de movimento ("quero ir para o centro", "me leva pro hospital").
    pedido_explicito diz se a frase começa pedindo um destino: só assim um destino troca a
    viagem em andamento (evita que "quanto falta pra chegar no centro" cancele a espera).
    """
    frase = normalizar(texto)
    intencao = next((nome for nome, padrao in _INTENCOES if padrao.search(frase)), None)
    achado = _DESTINO_VERBO.search(frase)
    if achado:
        explicito = bool(_PEDIDO_DE_DESTINO.match(frase))
        destino = achado.group("destino").strip()
        while (interno := _DESTINO_VERBO.search(destino)) is not None:  # "leva para chegar no centro"
            destino = interno.group("destino").strip()
        return ("destino" if explicito or intencao is None else intencao), destino, explicito
    if intencao is not None:
        return intencao, None, False
    curto = _DESTINO_CURTO.match(frase)
    if curto:
        return "destino", curto.group("destino").strip(), True
    return None, None, False


def destino_livre(texto: str) -> str:
    """Frase solta no começo da conversa ("hospital", "quero o centro") → o destino."""
    palavras = normalizar(texto).split()
    while palavras and palavras[0] in _ENCHIMENTO:
        palavras.pop(0)
    return " ".join(palavras)


@dataclass
class Sessao:
    id: str
    usuario: str | None = None
    estado: str = "inicio"
    rede: Rede | None = None
    destino_nome: str = ""
    planos: list[Plano] = field(default_factory=list)
    opcao: int = 0
    trecho: int = 0
    espera_id: str | None = None
    lat: float | None = None
    lon: float | None = None
    embarcou_em: float | None = None
    marcos: set[str] = field(default_factory=set)
    ultima_fala: str = ""
    cenario_demo: str = "auto"
    atualizado_em: float = field(default_factory=time.monotonic)
    trava: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @property
    def plano(self) -> Plano | None:
        return self.planos[self.opcao] if self.planos else None

    @property
    def trecho_atual(self) -> Trecho | None:
        plano = self.plano
        return plano.trechos[self.trecho] if plano and self.trecho < len(plano.trechos) else None

    @property
    def demo(self) -> bool:
        return self.rede is not None and self.rede.fonte == "demonstracao"


class Redes:
    """A rede de demonstração sempre; a da SPTrans quando o GTFS estiver carregado."""

    def __init__(self, demonstracao: Rede):
        self.demonstracao = demonstracao
        self.gtfs: Rede | None = None


class Conversa:
    def __init__(self, sonar, redes: Redes, http, geocodificador=None, tarefas: set | None = None, maximo: int = 2000):
        self.sonar = sonar
        self.redes = redes
        self.http = http
        self.geocodificador = geocodificador
        self.tarefas = tarefas if tarefas is not None else set()
        self.maximo = maximo
        self._sessoes: dict[str, Sessao] = {}
        self._trava = asyncio.Lock()

    # ------------------------------------------------------------------------------ sessões

    def _sessao(self, sessao_id: str | None, usuario: str | None) -> tuple[Sessao, bool]:
        agora = time.monotonic()
        validade = SESSAO_HORAS * 3600
        for chave in [k for k, v in self._sessoes.items() if agora - v.atualizado_em > validade]:
            del self._sessoes[chave]
        if sessao_id and sessao_id in self._sessoes:
            sessao = self._sessoes[sessao_id]
            sessao.atualizado_em = agora
            return sessao, False
        if len(self._sessoes) >= self.maximo:
            mais_antiga = min(self._sessoes.values(), key=lambda s: s.atualizado_em)
            del self._sessoes[mais_antiga.id]
        sessao = Sessao(id=str(uuid.uuid4()), usuario=usuario)
        self._sessoes[sessao.id] = sessao
        return sessao, True

    # ------------------------------------------------------------------------------ entrada

    async def tratar(
        self,
        sessao_id: str | None,
        evento: str,
        texto: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        usuario: str | None = None,
        cenario_demo: str = "auto",
    ) -> dict:
        async with self._trava:
            sessao, nova = self._sessao(sessao_id, usuario)
        async with sessao.trava:  # uma frase de cada vez por sessão (o app manda fala e posição juntos)
            sessao.cenario_demo = cenario_demo
            if lat is not None and lon is not None:
                sessao.lat, sessao.lon = lat, lon
            extras: dict = {}
            falas: list[str] = []

            falas.extend(await self._sincronizar(sessao))
            if evento == "abrir":
                falas.append(SAUDACAO if nova or sessao.estado == "inicio" else self._instrucao(sessao, "Continuando. "))
            elif evento == "fala" and texto:
                falas.extend(await self._ouvir(sessao, texto, extras))
            elif evento in ("posicao", "tick"):
                falas.extend(await self._acompanhar(sessao))

            fala = " ".join(f for f in falas if f).strip()
            if fala:
                sessao.ultima_fala = fala
            return self._resposta(sessao, fala, extras)

    def _resposta(self, sessao: Sessao, fala: str, extras: dict) -> dict:
        acompanhar = sessao.estado in ("indo_ao_ponto", "a_bordo") or (sessao.estado == "no_ponto" and sessao.demo)
        return {
            "sessao": sessao.id,
            "estado": sessao.estado,
            "fala": fala,
            "espera_id": sessao.espera_id,
            "plano": sessao.plano.como_dict() if sessao.plano else None,
            "trecho": sessao.trecho,
            "destino": sessao.destino_nome or None,
            "demo": sessao.demo,
            "acompanhar": acompanhar,
            "intervalo_s": 3 if sessao.demo else 10,
            **extras,
        }

    # ------------------------------------------------------------------------------ frases

    async def _ouvir(self, sessao: Sessao, texto: str, extras: dict) -> list[str]:
        intencao, destino, explicito = entender(texto)
        estado = sessao.estado
        em_viagem = estado in ("no_ponto", "a_bordo", "apos_ocorrencia", "indo_ao_ponto")

        if intencao == "ajuda":
            return [AJUDA]
        if intencao == "repetir":
            return [sessao.ultima_fala or SAUDACAO]
        if intencao == "cancelar":
            await self._encerrar_espera(sessao)
            self._recomecar(sessao)
            return ["Cancelado. Para onde você quer ir?"]
        if destino and (explicito or not em_viagem):
            return await self._planejar(sessao, destino, extras)
        if intencao == "destino":
            intencao = None  # no meio da viagem, "chegar no centro" é pergunta, não troca de destino

        if estado in ("inicio", "chegou"):
            if intencao in (None, "sim", "nao"):
                livre = destino_livre(texto)
                if livre:
                    return await self._planejar(sessao, livre, extras)
            return ["Primeiro me diga para onde você quer ir. Por exemplo: quero ir para o centro."]

        if estado == "confirmar_plano":
            if intencao == "sim":
                return await self._aceitar(sessao)
            if intencao == "outra_opcao":
                if sessao.opcao + 1 < len(sessao.planos):
                    sessao.opcao += 1
                    return ["Outra opção. " + await self._apresentar(sessao)]
                return ["Não tenho outra opção boa para esse destino. Diga sim para seguir com essa, ou outro destino."]
            if intencao == "nao":
                self._recomecar(sessao)
                return ["Tudo bem. Para onde você quer ir?"]
            return await self._planejar(sessao, texto, extras)

        if estado == "indo_ao_ponto":
            if intencao in ("cheguei", "sim"):
                return await self._conectar(sessao)
            if intencao == "quanto_falta":
                return [await self._previsao_falada(sessao)]
            if intencao == "localizar":
                return ["Diga 'cheguei' quando estiver no ponto: aí ele começa a apitar para você achar o poste."]
            return [self._instrucao(sessao)]

        if estado == "no_ponto":
            espera = await self._espera(sessao)
            if intencao == "embarquei":
                return await self._embarcou(sessao)
            if intencao == "reclamar" or (intencao == "sim" and self._pediu_reclamacao(espera)):
                return await self._reclamar(sessao, True)
            if intencao == "nao" and self._pediu_reclamacao(espera):
                return await self._reclamar(sessao, False)
            if intencao == "quanto_falta":
                return [await self._previsao_falada(sessao)]
            if intencao == "localizar":
                await self._chamar(self.sonar.localizar, sessao.espera_id)
                return ["O ponto vai apitar agora."]
            if intencao in ("proximo_passo", "cheguei", "sim", "nao", "esperar_de_novo", "outra_opcao", "desci"):
                return [self._instrucao(sessao)]
            return await self._agente(sessao, texto)

        if estado == "apos_ocorrencia":
            if intencao in ("esperar_de_novo", "sim", "cheguei"):
                return await self._conectar(sessao)
            if intencao == "nao":
                self._recomecar(sessao)
                return ["Tudo bem. Quando quiser, diga para onde você quer ir."]
            return [self._instrucao(sessao)]

        if estado == "a_bordo":
            if intencao == "desci":
                return await self._desceu(sessao)
            if intencao in ("quanto_falta", "proximo_passo"):
                return [self._instrucao(sessao)]
            return [self._instrucao(sessao)]

        if intencao == "embarquei" and sessao.espera_id:
            return await self._embarcou(sessao)
        return ["Não entendi. " + AJUDA]

    # ------------------------------------------------------------------------------ plano

    def _escolher_rede(self, sessao: Sessao, destino: str) -> Rede:
        gtfs = self.redes.gtfs
        if gtfs is None or _PALAVRA_DEMO.search(normalizar(destino)):
            return self.redes.demonstracao
        if self.redes.demonstracao.procurar_lugar(destino, minimo=0.99) and sessao.lat is None:
            return self.redes.demonstracao
        return gtfs

    async def _planejar(self, sessao: Sessao, destino: str, extras: dict) -> list[str]:
        destino = destino.strip()
        if not termos(destino):
            return ["Não entendi o destino. Diga, por exemplo: quero ir para o centro."]
        rede = self._escolher_rede(sessao, destino)
        if rede.fonte == "gtfs" and sessao.lat is None:
            extras["pedir_localizacao"] = True
            extras["repetir_texto"] = f"quero ir para {destino}"
            return ["Preciso da sua localização para achar o ponto mais perto. Permita a localização no aparelho."]

        lugar = await self._resolver_destino(rede, destino)
        if lugar is None:
            VIAGENS_PLANEJADAS.labels(rede.fonte, "destino_desconhecido").inc()
            if rede.fonte == "demonstracao":
                nomes = ", ".join(l.nome for l in rede.lugares[:5])
                return [f"Não encontrei {destino}. Na demonstração, dá para ir até: {nomes}."]
            return [f"Não encontrei {destino}. Diga o nome de um bairro, de um terminal, ou um endereço com número."]
        nome, dlat, dlon = lugar

        await self._encerrar_espera(sessao)
        origens = self._origens(rede, sessao)
        if not origens:
            VIAGENS_PLANEJADAS.labels(rede.fonte, "sem_ponto_perto").inc()
            return ["Não achei ponto de ônibus perto de você."]
        destinos = rede.proximos(dlat, dlon, 600) or rede.proximos(dlat, dlon, 1000)
        if sessao.lat is not None and distancia_m(sessao.lat, sessao.lon, dlat, dlon) < 500 and rede.fonte == "gtfs":
            return [f"{nome} fica {metros_falados(distancia_m(sessao.lat, sessao.lon, dlat, dlon))} de você. É mais rápido ir a pé."]
        planos = planejar(rede, origens, destinos)
        if not planos:
            VIAGENS_PLANEJADAS.labels(rede.fonte, "sem_caminho").inc()
            return [f"Não achei um caminho de ônibus até {nome} com no máximo uma baldeação."]

        VIAGENS_PLANEJADAS.labels(rede.fonte, "ok").inc()
        self._recomecar(sessao)
        sessao.rede, sessao.destino_nome, sessao.planos = rede, nome, planos
        sessao.estado = "confirmar_plano"
        return [await self._apresentar(sessao)]

    def _origens(self, rede: Rede, sessao: Sessao) -> list[tuple[PontoRede, float]]:
        if rede.fonte == "demonstracao":
            maquete = rede.pontos[demo.PARADA_DEMO]
            # na demonstração a viagem sai sempre da maquete (onde estão o Sonar Ponto e a câmera)
            if sessao.lat is not None:
                distancia = distancia_m(sessao.lat, sessao.lon, maquete.lat, maquete.lon)
                if distancia <= 1500:
                    return [(maquete, distancia)]
            return [(maquete, 0.0)]
        return rede.proximos(sessao.lat, sessao.lon, 600) or rede.proximos(sessao.lat, sessao.lon, 1000)

    async def _resolver_destino(self, rede: Rede, destino: str) -> tuple[str, float, float] | None:
        achados = rede.procurar_lugar(destino)
        if achados:
            lugar = achados[0][0]
            return lugar.nome, lugar.lat, lugar.lon
        if rede.fonte == "gtfs" and self.geocodificador is not None:
            resultados = await self.geocodificador.procurar(destino)
            if resultados:
                melhor = resultados[0]
                return melhor["nome"] or destino, melhor["lat"], melhor["lon"]
        return None

    async def _apresentar(self, sessao: Sessao) -> str:
        plano = sessao.plano
        partes = []
        if sessao.demo:
            partes.append("Modo demonstração.")
        partes.append(descrever(plano, sessao.destino_nome))
        minutos = await self._minutos_proximo(sessao, plano.trechos[0])
        if minutos is not None:
            partes.append(self._frase_previsao(plano.trechos[0].linha, minutos))
        partes.append("Quer ir? Diga sim, outra opção, ou outro destino.")
        return " ".join(partes)

    async def _aceitar(self, sessao: Sessao) -> list[str]:
        sessao.estado = "indo_ao_ponto"
        sessao.trecho = 0
        trecho = sessao.trecho_atual
        distancia = self._distancia_ao(sessao, trecho.embarque)
        if sessao.demo and (distancia is None or distancia > 1500):
            return [
                f"Combinado. Na demonstração, {ponto_falado(trecho.embarque.nome)} é a maquete. "
                "Diga 'cheguei' quando quiser começar."
            ]
        if distancia is not None and distancia <= RAIO_CHEGOU_M:
            return ["Combinado."] + await self._conectar(sessao, chegou_pelo_gps=True)
        return [
            f"Combinado. Vá até {ponto_falado(trecho.embarque.nome)}, {metros_falados(distancia or 0)}. "
            "Quando chegar, diga 'cheguei'. Se o GPS mostrar que você chegou, eu aviso o ponto sozinho."
        ]

    # ------------------------------------------------------------------------------ ponto e espera

    def _parada_do(self, sessao: Sessao, ponto: PontoRede) -> Parada:
        """A parada do cadastro para esse ponto (cria na hora para pontos do GTFS e da rede de demonstração)."""
        cadastro = self.sonar.paradas
        parada_id = ponto.id if sessao.demo else f"sp-{ponto.id}"
        if cadastro.existe(parada_id):
            return cadastro.obter(parada_id)
        linhas = tuple(
            Linha(codigo, destino)
            for codigo, destino in ((normalizar_linha(c), d) for c, d in sessao.rede.linhas_no_ponto(ponto.id))
            if codigo
        )
        return cadastro.registrar(
            Parada(parada_id, ponto.nome, ponto.codigo_sptrans, ponto.lat, ponto.lon, sessao.demo, linhas)
        )

    async def _conectar(self, sessao: Sessao, chegou_pelo_gps: bool = False) -> list[str]:
        trecho = sessao.trecho_atual
        if trecho is None:
            return ["Primeiro me diga para onde você quer ir."]
        parada = self._parada_do(sessao, trecho.embarque)
        linha = normalizar_linha(trecho.linha)
        if linha is None:
            return [f"Não consigo acompanhar a linha {trecho.linha} pelo Sonar. Confirme com o motorista."]
        distancia = self._distancia_ao(sessao, trecho.embarque)
        perto = distancia is not None and distancia <= 300
        try:
            espera = await run_in_threadpool(
                self.sonar.criar_espera,
                parada.id,
                [linha],
                "voz",
                sessao.usuario,
                sessao.lat if perto else None,
                sessao.lon if perto else None,
                sessao.demo,
            )
        except (NaoEncontrado, ValueError) as erro:
            log.warning("não consegui criar a espera: %s", erro)
            return ["Não consegui avisar o ponto agora. Tente dizer 'cheguei' de novo."]
        sessao.espera_id = espera["id"]
        sessao.estado = "no_ponto"
        sessao.marcos.clear()
        detector = await self._quem_detecta(parada.id)
        if sessao.demo:
            self._rodar_demo(sessao, espera["id"], parada.id, detector is not None)

        abertura = f"Você chegou a{ponto_falado(parada.nome)}. " if chegou_pelo_gps else ""
        if detector == "ponto":
            aviso_ponto = "Avisei o ponto: ele vai apitar para você achar o poste e piscar a luz para o motorista."
        elif detector == "camera":
            aviso_ponto = (
                "Avisei os motoristas que vêm para cá, e a câmera do ponto vai ler o letreiro de cada ônibus."
            )
        else:
            aviso_ponto = "Avisei os motoristas que vêm para cá."
        minutos = await self._minutos_proximo(sessao, trecho)
        previsao = f" {self._frase_previsao(linha, minutos)}" if minutos is not None else ""
        return [
            f"{abertura}{aviso_ponto} Estou esperando o {linha} com você.{previsao} "
            "Eu falo quando ele chegar. Quando entrar, diga: embarquei."
        ]

    async def _embarcou(self, sessao: Sessao) -> list[str]:
        try:
            await self._chamar(self.sonar.confirmar_embarque, sessao.espera_id, "voz")
        except Conflito:
            pass
        return self._comecar_viagem(sessao, "Boa viagem! ")

    def _comecar_viagem(self, sessao: Sessao, abertura: str) -> list[str]:
        sessao.estado = "a_bordo"
        sessao.embarcou_em = time.monotonic()
        sessao.marcos.discard("preparar")
        trecho = sessao.trecho_atual
        simulada = " Na demonstração, a viagem é simulada." if sessao.demo else ""
        return [
            f"{abertura}Desça n{ponto_falado(trecho.desembarque.nome)}, {paradas_faladas(trecho.paradas)}. "
            f"Eu aviso quando estiver chegando.{simulada}"
        ]

    async def _reclamar(self, sessao: Sessao, consentimento: bool) -> list[str]:
        try:
            await self._chamar(self.sonar.registrar_nao_parou, sessao.espera_id, consentimento)
        except Conflito:
            return ["Essa espera já terminou. Diga 'esperar de novo' para esperar o próximo."]
        sessao.estado = "apos_ocorrencia"
        linha = sessao.trecho_atual.linha if sessao.trecho_atual else "ônibus"
        if consentimento:
            return [
                "Registrei a reclamação com as evidências do ponto. O robô vai enviar e eu falo o protocolo assim que "
                f"chegar. Quer esperar o próximo {linha}? Diga: esperar de novo."
            ]
        return [f"Tudo bem, fica só no relatório anônimo. Quer esperar o próximo {linha}? Diga: esperar de novo."]

    @staticmethod
    def _pediu_reclamacao(espera: dict | None) -> bool:
        ocorrencia = (espera or {}).get("ocorrencia") or {}
        return ocorrencia.get("status") == "aguardando_consentimento"

    async def _encerrar_espera(self, sessao: Sessao) -> None:
        if sessao.espera_id:
            try:
                await self._chamar(self.sonar.cancelar_espera, sessao.espera_id)
            except (Conflito, NaoEncontrado):
                pass
            sessao.espera_id = None

    # ------------------------------------------------------------------------------ viagem

    async def _acompanhar(self, sessao: Sessao) -> list[str]:
        trecho = sessao.trecho_atual
        if trecho is None:
            return []
        if sessao.estado == "indo_ao_ponto" and not sessao.demo:
            distancia = self._distancia_ao(sessao, trecho.embarque)
            if distancia is not None and distancia <= RAIO_CHEGOU_M:
                return await self._conectar(sessao, chegou_pelo_gps=True)
            return []
        if sessao.estado != "a_bordo":
            return []
        if sessao.demo:
            fator = 1 / max(self.sonar.cfg.demo_velocidade, 0.01)
            decorrido = time.monotonic() - (sessao.embarcou_em or time.monotonic())
            if decorrido >= DEMO_DESCER_S * fator:
                return await self._desceu(sessao, aviso="Chegamos. ")
            if decorrido >= DEMO_PREPARAR_S * fator and "preparar" not in sessao.marcos:
                sessao.marcos.add("preparar")
                return [self._frase_preparar(trecho)]
            return []
        distancia = self._distancia_ao(sessao, trecho.desembarque)
        if distancia is None:
            return []
        if distancia <= RAIO_DESCER_M:
            return await self._desceu(sessao, aviso="Chegamos. ")
        if distancia <= RAIO_PREPARAR_M and "preparar" not in sessao.marcos:
            sessao.marcos.add("preparar")
            return [self._frase_preparar(trecho)]
        return []

    @staticmethod
    def _frase_preparar(trecho: Trecho) -> str:
        return f"Prepare-se: a próxima parada é {trecho.desembarque.nome}. Dê o sinal para descer."

    async def _desceu(self, sessao: Sessao, aviso: str = "") -> list[str]:
        trecho = sessao.trecho_atual
        if trecho is None:
            return []
        sessao.trecho += 1
        sessao.espera_id = None
        sessao.embarcou_em = None
        proximo = sessao.trecho_atual
        if proximo is not None:
            descer = f"{aviso}Desça agora: você está n{ponto_falado(trecho.desembarque.nome)}. Agora vamos pegar o {proximo.linha}."
            return [descer] + await self._conectar(sessao)
        plano = sessao.plano
        sessao.estado = "chegou"
        resto = (
            f" {sessao.destino_nome} fica {metros_falados(plano.caminhada_fim_m)} daqui."
            if plano and plano.caminhada_fim_m >= 30
            else ""
        )
        return [
            f"{aviso}Desça agora. Você chegou a{ponto_falado(trecho.desembarque.nome)}.{resto} "
            "Boa caminhada! Quando quiser, toque na tela e diga um novo destino."
        ]

    # ------------------------------------------------------------------------------ apoio

    async def _sincronizar(self, sessao: Sessao) -> list[str]:
        """Acompanha o que aconteceu na espera fora da conversa (botões, simuladores, tempo)."""
        if not sessao.espera_id or sessao.estado != "no_ponto":
            return []
        espera = await self._espera(sessao)
        if espera is None:
            sessao.espera_id = None
            sessao.estado = "indo_ao_ponto"
            return []
        status = espera["status"]
        if status == "embarcou":
            return self._comecar_viagem(sessao, "")
        if status == "nao_parou":
            sessao.estado = "apos_ocorrencia"
        elif status in ("cancelada", "expirada"):
            sessao.espera_id = None
            sessao.estado = "indo_ao_ponto"
        return []

    async def _espera(self, sessao: Sessao) -> dict | None:
        if not sessao.espera_id:
            return None
        try:
            return await run_in_threadpool(self.sonar.obter_espera, sessao.espera_id)
        except NaoEncontrado:
            return None

    async def _chamar(self, funcao, *argumentos):
        return await run_in_threadpool(funcao, *argumentos)

    async def _agente(self, sessao: Sessao, texto: str) -> list[str]:
        """Pergunta livre no meio da espera: vai para a IA generativa, com o ponto como contexto."""
        espera = await self._espera(sessao)
        parada_id = espera["parada_id"] if espera else None
        resposta = await perguntar_ia(self.sonar, self.http, texto, parada_id)
        return [resposta.resposta_falada]

    async def _quem_detecta(self, parada_id: str) -> str | None:
        """Quem vê o ônibus chegar neste ponto: o Sonar Ponto, a câmera sozinha (ex.: o celular) ou ninguém."""
        try:
            estado = await run_in_threadpool(self.sonar.estado_parada, parada_id)
        except Exception:  # noqa: BLE001 - sem o estado, segue como se não houvesse hardware
            return None
        dispositivos = estado.get("dispositivos") or {}  # {"ponto": {...}, "camera": {...}}
        if (dispositivos.get("ponto") or {}).get("online"):
            return "ponto"
        camera = dispositivos.get("camera") or {}
        if camera.get("online") and camera.get("sem_ponto"):
            return "camera"
        return None

    def _rodar_demo(self, sessao: Sessao, espera_id: str, parada_id: str, com_hardware: bool) -> None:
        cenario = sessao.cenario_demo
        if cenario == "auto":
            # com o Sonar Ponto (ou a câmera sozinha) ligado na maquete, quem detecta o ônibus é ele
            cenario = "maquete" if com_hardware else "embarque"
        if cenario == "maquete" and parada_id != demo.PARADA_DEMO:
            cenario = "embarque"  # a maquete só existe no ponto de demonstração
        tarefa = asyncio.create_task(demo.executar(self.sonar, espera_id, cenario, self.sonar.cfg.demo_velocidade))
        self.tarefas.add(tarefa)
        tarefa.add_done_callback(self.tarefas.discard)

    def _distancia_ao(self, sessao: Sessao, ponto: PontoRede) -> float | None:
        if sessao.lat is None or sessao.lon is None:
            return None
        return distancia_m(sessao.lat, sessao.lon, ponto.lat, ponto.lon)

    async def _minutos_proximo(self, sessao: Sessao, trecho: Trecho) -> int | None:
        linha = normalizar_linha(trecho.linha)
        try:
            if sessao.demo:
                parada = self._parada_do(sessao, trecho.embarque)
                veiculos = await self.sonar.previsao(parada.id)
                if not veiculos and parada.id != demo.PARADA_DEMO:
                    return 4  # ponto fictício sem roteiro ainda: previsão de exemplo
            elif trecho.embarque.codigo_sptrans and self.sonar.olhovivo.configurado:
                veiculos = await self.sonar.olhovivo.previsao_parada(trecho.embarque.codigo_sptrans)
            else:
                return None
        except (OlhoVivoIndisponivel, NaoEncontrado):
            return None
        minutos = [v.minutos for v in veiculos if v.linha == linha]
        return min(minutos) if minutos else None

    @staticmethod
    def _frase_previsao(linha: str, minutos: int) -> str:
        if minutos <= 0:
            return f"O {linha} está chegando agora."
        return f"O próximo {linha} chega em {minutos} {'minuto' if minutos == 1 else 'minutos'}."

    async def _previsao_falada(self, sessao: Sessao) -> str:
        trecho = sessao.trecho_atual
        if trecho is None:
            return "Primeiro me diga para onde você quer ir."
        minutos = await self._minutos_proximo(sessao, trecho)
        if minutos is None:
            return f"Ainda não tenho a previsão do {trecho.linha}."
        return self._frase_previsao(trecho.linha, minutos)

    def _instrucao(self, sessao: Sessao, abertura: str = "") -> str:
        trecho = sessao.trecho_atual
        estado = sessao.estado
        if estado == "confirmar_plano" and sessao.plano:
            return abertura + descrever(sessao.plano, sessao.destino_nome) + " Quer ir? Diga sim."
        if trecho is None:
            return abertura + "Diga para onde você quer ir."
        if estado == "indo_ao_ponto":
            distancia = self._distancia_ao(sessao, trecho.embarque)
            onde = f", {metros_falados(distancia)}" if distancia is not None and distancia < 1500 else ""
            return f"{abertura}Vá até {ponto_falado(trecho.embarque.nome)}{onde}, e pegue o {trecho.linha}. Ao chegar, diga: cheguei."
        if estado == "no_ponto":
            return f"{abertura}Estamos esperando o {trecho.linha} n{ponto_falado(trecho.embarque.nome)}. Eu falo quando ele chegar."
        if estado == "apos_ocorrencia":
            return f"{abertura}Quer esperar o próximo {trecho.linha}? Diga: esperar de novo. Ou diga outro destino."
        if estado == "a_bordo":
            return f"{abertura}Você está no {trecho.linha}. Desça n{ponto_falado(trecho.desembarque.nome)}. Eu aviso quando estiver chegando."
        return abertura + "Diga para onde você quer ir."

    def _recomecar(self, sessao: Sessao) -> None:
        sessao.estado = "inicio"
        sessao.planos = []
        sessao.opcao = 0
        sessao.trecho = 0
        sessao.destino_nome = ""
        sessao.espera_id = None
        sessao.embarcou_em = None
        sessao.marcos.clear()
