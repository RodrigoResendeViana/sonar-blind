"""Regras do Sonar: espera, aviso ao motorista, detecção no ponto, embarque e ocorrência.

Tudo o que muda o estado passa por _transacao(): grava no banco, registra o evento
no log (tabela eventos) e só depois de confirmar a transação publica no SSE e no MQTT.
"""

import logging
import math
import re
import secrets
import threading
import uuid
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from .barramento import Barramento
from .config import Settings
from .db import Dispositivo, Espera, Evento, Ocorrencia, agora, iso
from .metricas import (
    AVISOS_CIENTES,
    AVISOS_ENVIADOS,
    DISPOSITIVO_ONLINE,
    DISPOSITIVO_ULTIMO_SINAL,
    EMBARQUES,
    ESPERAS_ATIVAS,
    ESPERAS_CRIADAS,
    OCORRENCIAS,
)
from .mqtt_ponte import Publicador, PublicadorMemoria
from .olhovivo import ClienteOlhoVivo, OlhoVivoIndisponivel, Veiculo
from .paradas import CadastroParadas, Parada, distancia_m, normalizar_linha
from .seguranca import hash_usuario

log = logging.getLogger("sonar")

TERMINAIS = {"embarcou", "nao_parou", "cancelada", "expirada"}
OCORRENCIA_FECHADA = {"enviada", "inconclusiva", "duplicada", "erro", "anonima", "descartada"}
STATUS_DO_ROBO = {"em_processamento", "enviada", "inconclusiva", "duplicada", "erro"}
ENCERRAM_STREAM = {
    "embarque_confirmado",
    "ocorrencia_registrada",
    "ocorrencia_protocolo",
    "ocorrencia_inconclusiva",
    "cancelada",
    "expirada",
}
LIMIAR_PAROU_S = 3.0
CONFIANCA_MINIMA = 0.6
PADRAO_REF = re.compile(r"^[A-Za-z0-9-]{1,40}$")

FALA_SEM_CAMERA = (
    "A câmera do ponto está fora do ar. Sem confirmação visual: confirme a linha com o motorista antes de embarcar."
)


class NaoEncontrado(Exception):
    pass


class Conflito(Exception):
    pass


def _de_iso(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return None


def _numero(valor, padrao: float) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return padrao


def _lista(itens: list[str]) -> str:
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


def fala_previsao(v: Veiculo) -> str:
    sentido = f", sentido {v.destino}" if v.destino else ""
    if v.minutos <= 0:
        quando = "está chegando"
    elif v.minutos == 1:
        quando = "chega em 1 minuto"
    else:
        quando = f"chega em {v.minutos} minutos"
    extra = " Ônibus com acessibilidade." if v.acessivel else ""
    return f"A linha {v.linha}{sentido}, {quando}.{extra}"


class _Saida:
    """O que publicar depois que a transação for confirmada."""

    def __init__(self) -> None:
        self.sse: list[tuple[str, dict]] = []
        self.mqtt: list[tuple[str, dict, bool]] = []

    def despachar(self, barramento: Barramento, publicador: Publicador) -> None:
        for canal, evento in self.sse:
            barramento.publicar(canal, evento)
        for topico, dados, retido in self.mqtt:
            try:
                publicador.publicar(topico, dados, retido)
            except Exception:
                log.exception("falha ao publicar em %s", topico)


class Sonar:
    def __init__(
        self,
        cfg: Settings,
        sessoes: sessionmaker,
        paradas: CadastroParadas,
        olhovivo: ClienteOlhoVivo,
        barramento: Barramento,
        publicador: Publicador | None = None,
    ):
        self.cfg = cfg
        self._sessoes = sessoes
        self.paradas = paradas
        self.olhovivo = olhovivo
        self.barramento = barramento
        self.publicador: Publicador = publicador or PublicadorMemoria()
        self.previsao_demo: list[Veiculo] = []
        self._trava = threading.RLock()
        self._fechado = False
        if not cfg.sal_hash:
            log.warning("SONAR_SAL_HASH não definido: usando um sal temporário")
        self._sal = cfg.sal_hash or secrets.token_hex(16)

    # ------------------------------------------------------------------ infraestrutura

    def fechar(self, engine) -> None:
        """Fecha o banco só quando nenhuma thread está no meio de uma operação."""
        with self._trava:
            self._fechado = True
            engine.dispose()

    def _abrir(self) -> Session:
        if self._fechado:
            raise RuntimeError("serviço encerrado")
        return self._sessoes()

    @contextmanager
    def _leitura(self):
        with self._trava:
            sessao: Session = self._abrir()
            try:
                yield sessao
            finally:
                sessao.close()

    @contextmanager
    def _transacao(self):
        saida = _Saida()
        with self._trava:
            sessao: Session = self._abrir()
            try:
                yield sessao, saida
                sessao.commit()
            except BaseException:
                sessao.rollback()
                raise
            finally:
                sessao.close()
        saida.despachar(self.barramento, self.publicador)

    @staticmethod
    def evento_dict(evento: Evento) -> dict:
        return {
            "id": evento.id,
            "tipo": evento.tipo,
            "fala": evento.fala,
            "dados": evento.dados or {},
            "em": iso(evento.criado_em),
        }

    def _emitir(self, s: Session, saida: _Saida, espera: Espera, tipo: str, fala: str | None, **dados) -> Evento:
        evento = Evento(
            espera_id=espera.id, parada_id=espera.parada_id, tipo=tipo, fala=fala, dados=dados, criado_em=agora()
        )
        s.add(evento)
        s.flush()
        saida.sse.append((f"espera:{espera.id}", self.evento_dict(evento)))
        return evento

    @staticmethod
    def _ativas(s: Session, parada_id: str | None = None, demo: bool | None = None) -> list[Espera]:
        consulta = select(Espera).where(Espera.status == "aguardando")
        if parada_id is not None:
            consulta = consulta.where(Espera.parada_id == parada_id)
        if demo is not None:
            consulta = consulta.where(Espera.demo.is_(demo))
        return list(s.scalars(consulta.order_by(Espera.criado_em)))

    @staticmethod
    def _obter(s: Session, espera_id: str) -> Espera:
        espera = s.get(Espera, espera_id)
        if espera is None:
            raise NaoEncontrado("espera não encontrada")
        return espera

    def _parada_nome(self, parada_id: str) -> str:
        return self.paradas.obter(parada_id).nome if self.paradas.existe(parada_id) else parada_id

    def _espera_dict(self, s: Session, e: Espera) -> dict:
        ocorrencia = s.scalars(
            select(Ocorrencia).where(Ocorrencia.espera_id == e.id).order_by(Ocorrencia.id.desc())
        ).first()
        previsao = e.ultima_previsao if e.ultima_previsao and "linha" in e.ultima_previsao else None
        return {
            "id": e.id,
            "parada_id": e.parada_id,
            "parada_nome": self._parada_nome(e.parada_id),
            "linhas": e.linhas_alvo,
            "status": e.status,
            "demo": e.demo,
            "criado_em": iso(e.criado_em),
            "expira_em": iso(e.expira_em),
            "encerrado_em": iso(e.encerrado_em),
            "previsao": previsao,
            "aviso": (
                {
                    "enviado_em": iso(e.aviso_enviado_em),
                    "prefixo": e.prefixo_avisado,
                    "linha": e.linha_avisada,
                    "ciente_em": iso(e.ciente_em),
                }
                if e.aviso_enviado_em
                else None
            ),
            "passagem": (
                {
                    "em": iso(e.passagem_em),
                    "linha": e.passagem_linha,
                    "confianca": e.passagem_confianca,
                    "tempo_parado_s": e.passagem_tempo_parado_s,
                    "parou": e.passagem_parou,
                    "camera_ok": e.passagem_camera_ok,
                }
                if e.passagem_em
                else None
            ),
            "embarque": (
                {"em": iso(e.embarque_em), "origem": e.embarque_origem, "validado_por_camera": e.validado_por_camera}
                if e.embarque_em
                else None
            ),
            "ocorrencia": (
                {
                    "id": ocorrencia.id,
                    "status": ocorrencia.status,
                    "protocolo": ocorrencia.protocolo,
                    "consentimento": ocorrencia.consentimento,
                }
                if ocorrencia
                else None
            ),
        }

    def _comandar_ponto(self, s: Session, saida: _Saida, parada_id: str) -> None:
        """Mantém o Sonar Ponto em sincronia com as esperas abertas (mensagem retida)."""
        ativas = self._ativas(s, parada_id)
        if ativas:
            comando = {
                "acao": "ativar",
                "espera_id": ativas[-1].id,
                "linhas_alvo": sorted({linha for e in ativas for linha in e.linhas_alvo}),
                "expira_em": iso(max(e.expira_em for e in ativas)),
            }
        else:
            comando = {"acao": "desativar"}
        saida.mqtt.append((f"sonar/parada/{parada_id}/cmd", comando, True))
        saida.sse.append((f"parada:{parada_id}", {"tipo": "cmd", "dados": comando, "em": iso(agora())}))

    def _evidencias(self, e: Espera) -> dict:
        parada = self.paradas.obter(e.parada_id) if self.paradas.existe(e.parada_id) else None
        return {
            "parada": {
                "id": e.parada_id,
                "nome": parada.nome if parada else None,
                "codigo_sptrans": parada.codigo_sptrans if parada else None,
            },
            "linhas_alvo": e.linhas_alvo,
            "espera_criada_em": iso(e.criado_em),
            "passagem": (
                {
                    "em": iso(e.passagem_em),
                    "linha": e.passagem_linha,
                    "confianca": e.passagem_confianca,
                    "tempo_parado_s": e.passagem_tempo_parado_s,
                    "parou": e.passagem_parou,
                    "camera_ok": e.passagem_camera_ok,
                }
                if e.passagem_em
                else None
            ),
            "aviso": (
                {
                    "enviado_em": iso(e.aviso_enviado_em),
                    "prefixo": e.prefixo_avisado,
                    "linha": e.linha_avisada,
                    "ciente_em": iso(e.ciente_em),
                }
                if e.aviso_enviado_em
                else None
            ),
            "previsao": e.ultima_previsao,
            "embarque_confirmado": e.embarque_em is not None,
        }

    def _ocorrencia_pendente(self, s: Session, e: Espera) -> Ocorrencia | None:
        return s.scalars(
            select(Ocorrencia)
            .where(Ocorrencia.espera_id == e.id, Ocorrencia.status == "aguardando_consentimento")
            .order_by(Ocorrencia.id.desc())
        ).first()

    def _garantir_ocorrencia(self, s: Session, e: Espera, status: str, consentimento: bool = False) -> Ocorrencia:
        ocorrencia = self._ocorrencia_pendente(s, e)
        if ocorrencia is None:
            ocorrencia = Ocorrencia(
                espera_id=e.id,
                parada_id=e.parada_id,
                status=status,
                consentimento=consentimento,
                evidencias={},
                criado_em=agora(),
            )
            s.add(ocorrencia)
        ocorrencia.status = status
        ocorrencia.consentimento = consentimento
        ocorrencia.linha = e.passagem_linha or e.linha_avisada or (e.linhas_alvo[0] if e.linhas_alvo else None)
        ocorrencia.prefixo = e.prefixo_avisado or (e.ultima_previsao or {}).get("prefixo")
        ocorrencia.evidencias = self._evidencias(e)
        ocorrencia.atualizado_em = agora()
        s.flush()
        return ocorrencia

    def _fechar_ocorrencia_pendente(self, s: Session, e: Espera, novo_status: str) -> None:
        ocorrencia = self._ocorrencia_pendente(s, e)
        if ocorrencia is not None:
            ocorrencia.status = novo_status
            ocorrencia.atualizado_em = agora()

    @staticmethod
    def stream_encerrado(estado: dict) -> bool:
        if estado["status"] not in TERMINAIS:
            return False
        if estado["status"] != "nao_parou":
            return True
        ocorrencia = estado.get("ocorrencia")
        return ocorrencia is None or ocorrencia["status"] in OCORRENCIA_FECHADA

    def verificar_banco(self) -> None:
        with self._leitura() as s:
            s.execute(text("SELECT 1"))

    # ------------------------------------------------------------------ esperas

    def criar_espera(
        self,
        parada_id: str,
        linhas: list[str],
        origem: str = "toque",
        usuario: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        demo: bool = False,
    ) -> dict:
        if not self.paradas.existe(parada_id):
            raise NaoEncontrado("parada não encontrada")
        parada = self.paradas.obter(parada_id)
        normalizadas: list[str] = []
        for linha in linhas:
            codigo = normalizar_linha(linha)
            if codigo is None:
                raise ValueError(f"linha inválida: {linha!r}")
            if codigo not in normalizadas:
                normalizadas.append(codigo)
        if not normalizadas:
            raise ValueError("informe ao menos uma linha")
        distancia = None
        if lat is not None and lon is not None and parada.lat is not None and parada.lon is not None:
            distancia = round(distancia_m(lat, lon, parada.lat, parada.lon))
        duracao = timedelta(minutes=10 if demo else self.cfg.espera_minutos)

        with self._transacao() as (s, saida):
            instante = agora()
            espera = Espera(
                id=str(uuid.uuid4()),
                parada_id=parada.id,
                linhas_alvo=normalizadas,
                status="aguardando",
                demo=demo,
                origem=origem,
                usuario_hash=hash_usuario(self._sal, usuario),
                criado_em=instante,
                expira_em=instante + duracao,
            )
            s.add(espera)
            s.flush()
            self._emitir(
                s,
                saida,
                espera,
                "ponto_ativado",
                self._fala_chegada(parada, distancia),
                parada=parada.nome,
                distancia_m=distancia,
                linhas=normalizadas,
            )
            ponto = s.get(Dispositivo, f"ponto:{parada.id}")
            if ponto is not None and not ponto.online:
                self._emitir(
                    s,
                    saida,
                    espera,
                    "ponto_offline",
                    "O Sonar Ponto deste ponto está sem conexão. Vou usar só a previsão do Olho Vivo.",
                )
            camera = s.get(Dispositivo, f"camera:{parada.id}")
            if camera is not None and not camera.online:
                self._emitir(s, saida, espera, "sem_confirmacao_visual", FALA_SEM_CAMERA)
            self._comandar_ponto(s, saida, parada.id)
            resultado = self._espera_dict(s, espera)
        ESPERAS_CRIADAS.labels(str(demo).lower()).inc()
        return resultado

    @staticmethod
    def _fala_chegada(parada: Parada, distancia: int | None) -> str:
        bip = "O Sonar Ponto vai apitar para mostrar onde fica o poste."
        if distancia is None:
            return f"Espera iniciada no ponto {parada.nome}. {bip}"
        if distancia <= 60:
            return f"Você está no ponto certo: {parada.nome}. {bip}"
        return f"Atenção: você parece estar a {distancia} metros do ponto {parada.nome}. Confira antes de esperar."

    def obter_espera(self, espera_id: str) -> dict:
        with self._leitura() as s:
            return self._espera_dict(s, self._obter(s, espera_id))

    def eventos_desde(self, espera_id: str, ultimo_id: int = 0) -> tuple[dict, list[dict]]:
        with self._leitura() as s:
            espera = self._obter(s, espera_id)
            eventos = s.scalars(
                select(Evento).where(Evento.espera_id == espera_id, Evento.id > ultimo_id).order_by(Evento.id)
            )
            return self._espera_dict(s, espera), [self.evento_dict(ev) for ev in eventos]

    def localizar(self, espera_id: str) -> dict:
        with self._transacao() as (s, saida):
            espera = self._obter(s, espera_id)
            if espera.status in TERMINAIS:
                raise Conflito("a espera já foi encerrada")
            comando = {"acao": "localizar", "espera_id": espera.id}
            saida.mqtt.append((f"sonar/parada/{espera.parada_id}/cmd", comando, False))
            saida.sse.append((f"parada:{espera.parada_id}", {"tipo": "cmd", "dados": comando, "em": iso(agora())}))
            self._emitir(s, saida, espera, "localizar", "O Sonar Ponto vai apitar agora.")
            return self._espera_dict(s, espera)

    def confirmar_embarque(self, espera_id: str, origem: str = "toque", horario: datetime | None = None) -> dict:
        with self._transacao() as (s, saida):
            espera = self._obter(s, espera_id)
            if espera.status == "embarcou":
                return self._espera_dict(s, espera)
            if espera.status in TERMINAIS:
                raise Conflito(f"a espera já foi encerrada ({espera.status})")
            instante = agora()
            if horario is None or abs((horario - instante).total_seconds()) > 900:
                horario = instante
            espera.status = "embarcou"
            espera.encerrado_em = instante
            espera.embarque_em = horario
            espera.embarque_origem = origem
            perto_da_passagem = (
                espera.passagem_em is not None and abs((horario - espera.passagem_em).total_seconds()) <= 600
            )
            espera.validado_por_camera = bool(
                perto_da_passagem and espera.passagem_linha in espera.linhas_alvo and espera.passagem_camera_ok
            )
            # se o último ônibus visto "passou direto" e mesmo assim houve embarque, a ocorrência era alarme falso
            self._fechar_ocorrencia_pendente(s, espera, "descartada" if espera.passagem_parou is False else "anonima")
            fala = "Boa viagem! Embarque registrado" + (
                " e confirmado pela câmera do ponto." if espera.validado_por_camera else "."
            )
            self._emitir(
                s,
                saida,
                espera,
                "embarque_confirmado",
                fala,
                validado_por_camera=espera.validado_por_camera,
                origem=origem,
            )
            self._comandar_ponto(s, saida, espera.parada_id)
            resultado = self._espera_dict(s, espera)
        EMBARQUES.labels(str(resultado["embarque"]["validado_por_camera"]).lower()).inc()
        return resultado

    def registrar_nao_parou(self, espera_id: str, consentimento: bool) -> dict:
        with self._transacao() as (s, saida):
            espera = self._obter(s, espera_id)
            if espera.status in TERMINAIS:
                raise Conflito(f"a espera já foi encerrada ({espera.status})")
            espera.status = "nao_parou"
            espera.encerrado_em = agora()
            ocorrencia = self._garantir_ocorrencia(
                s, espera, status="pendente" if consentimento else "anonima", consentimento=consentimento
            )
            fala = "Registrei que o ônibus não parou. " + (
                "Vou enviar a reclamação e te aviso o protocolo."
                if consentimento
                else "Ela entra só no relatório anônimo para a SPTrans."
            )
            self._emitir(
                s,
                saida,
                espera,
                "ocorrencia_registrada",
                fala,
                ocorrencia_id=ocorrencia.id,
                consentimento=consentimento,
            )
            self._comandar_ponto(s, saida, espera.parada_id)
            resultado = self._espera_dict(s, espera)
        OCORRENCIAS.labels(str(consentimento).lower()).inc()
        return resultado

    def cancelar_espera(self, espera_id: str) -> dict:
        with self._transacao() as (s, saida):
            espera = self._obter(s, espera_id)
            if espera.status not in TERMINAIS:
                espera.status = "cancelada"
                espera.encerrado_em = agora()
                self._fechar_ocorrencia_pendente(s, espera, "anonima")
                self._emitir(s, saida, espera, "cancelada", "Espera cancelada.")
                self._comandar_ponto(s, saida, espera.parada_id)
            return self._espera_dict(s, espera)

    # ------------------------------------------------------------------ previsão e aviso ao motorista

    async def previsao(self, parada_id: str) -> list[Veiculo]:
        if not self.paradas.existe(parada_id):
            raise NaoEncontrado("parada não encontrada")
        parada = self.paradas.obter(parada_id)
        if parada.demo:
            return list(self.previsao_demo)
        if not parada.codigo_sptrans:
            raise OlhoVivoIndisponivel("parada sem código da SPTrans cadastrado")
        return await self.olhovivo.previsao_parada(parada.codigo_sptrans)

    def paradas_com_espera_real(self) -> list[str]:
        with self._leitura() as s:
            ids = {e.parada_id for e in self._ativas(s, demo=False)}
        return sorted(
            pid for pid in ids if self.paradas.existe(pid) and self.paradas.obter(pid).codigo_sptrans
        )

    def processar_previsao(self, parada_id: str, veiculos: list[Veiculo], demo: bool | None = False) -> None:
        with self._transacao() as (s, saida):
            for espera in self._ativas(s, parada_id, demo):
                self._aplicar_previsao(s, saida, espera, veiculos)

    def _aplicar_previsao(self, s: Session, saida: _Saida, e: Espera, veiculos: list[Veiculo]) -> None:
        anterior = dict(e.ultima_previsao or {})
        instante = agora()
        alvo = [v for v in veiculos if v.linha in e.linhas_alvo]
        if not alvo:
            if not anterior.get("sem_previsao"):
                e.ultima_previsao = {"sem_previsao": True, "emitido_em": iso(instante)}
                self._emitir(
                    s,
                    saida,
                    e,
                    "previsao",
                    f"Sem previsão agora para {_lista(e.linhas_alvo)} neste ponto.",
                    sem_previsao=True,
                )
            return
        veiculo = alvo[0]
        emitido_em = _de_iso(anterior.get("emitido_em"))
        intervalo = 5 if e.demo else 50
        deve_emitir = anterior.get("prefixo") != veiculo.prefixo or (
            anterior.get("minutos") != veiculo.minutos
            and (veiculo.minutos <= 2 or emitido_em is None or (instante - emitido_em).total_seconds() >= intervalo)
        )
        novo = {**veiculo.como_dict(), "atualizado_em": iso(instante), "emitido_em": anterior.get("emitido_em")}
        if deve_emitir:
            novo["emitido_em"] = iso(instante)
            self._emitir(s, saida, e, "previsao", fala_previsao(veiculo), **veiculo.como_dict())
        e.ultima_previsao = novo
        if e.aviso_enviado_em is None and veiculo.minutos <= self.cfg.aviso_minutos:
            self._avisar_motorista(s, saida, e, veiculo)

    def _avisar_motorista(self, s: Session, saida: _Saida, e: Espera, veiculo: Veiculo) -> None:
        if not PADRAO_REF.fullmatch(veiculo.prefixo):
            log.warning("prefixo inválido vindo da previsão: %r", veiculo.prefixo)
            return
        paradas_ate = max(1, math.ceil(veiculo.minutos / 2))  # estimativa: ~2 min por parada
        instante = agora()
        e.aviso_enviado_em = instante
        e.prefixo_avisado = veiculo.prefixo
        e.linha_avisada = veiculo.linha
        alerta = {
            "espera_id": e.id,
            "parada_nome": self._parada_nome(e.parada_id),
            "paradas_ate": paradas_ate,
            "linha": veiculo.linha,
        }
        saida.mqtt.append((f"sonar/onibus/{veiculo.prefixo}/alerta", alerta, False))
        saida.sse.append(("motorista", {"tipo": "alerta", "prefixo": veiculo.prefixo, "em": iso(instante), **alerta}))
        self._emitir(
            s,
            saida,
            e,
            "aviso_enviado",
            f"Estou avisando o motorista da linha {veiculo.linha} que você está no ponto.",
            prefixo=veiculo.prefixo,
            paradas_ate=paradas_ate,
        )
        AVISOS_ENVIADOS.inc()

    def avisar_olhovivo_indisponivel(self, parada_id: str) -> None:
        with self._transacao() as (s, saida):
            for espera in self._ativas(s, parada_id, demo=False):
                anterior = dict(espera.ultima_previsao or {})
                ultimo = _de_iso(anterior.get("indisponivel_em"))
                if ultimo is None or (agora() - ultimo).total_seconds() >= 300:
                    anterior["indisponivel_em"] = iso(agora())
                    espera.ultima_previsao = anterior
                    self._emitir(
                        s,
                        saida,
                        espera,
                        "olhovivo_indisponivel",
                        "A previsão do Olho Vivo está fora do ar agora. Continuo atento pela câmera do ponto.",
                    )

    def registrar_ciente(self, prefixo: str, dados: dict) -> bool:
        espera_id = dados.get("espera_id")
        with self._transacao() as (s, saida):
            espera = s.get(Espera, espera_id) if isinstance(espera_id, str) else None
            if espera is None:
                espera = s.scalars(
                    select(Espera)
                    .where(Espera.status == "aguardando", Espera.prefixo_avisado == prefixo)
                    .order_by(Espera.aviso_enviado_em.desc())
                ).first()
            if espera is None or espera.status in TERMINAIS or espera.prefixo_avisado != prefixo:
                return False
            if espera.ciente_em is None:
                espera.ciente_em = agora()
                self._emitir(
                    s,
                    saida,
                    espera,
                    "motorista_ciente",
                    "O motorista foi avisado e confirmou.",
                    prefixo=prefixo,
                    simulado=bool(dados.get("simulado")),
                )
                saida.sse.append(
                    ("motorista", {"tipo": "ciente_registrado", "prefixo": prefixo, "espera_id": espera.id, "em": iso(agora())})
                )
                AVISOS_CIENTES.inc()
            return True

    def alertas_pendentes(self) -> list[dict]:
        """Alertas dos últimos 10 min ainda sem "ciente" (tela do motorista simulado)."""
        desde = agora() - timedelta(minutes=10)
        with self._leitura() as s:
            eventos = s.scalars(
                select(Evento).where(Evento.tipo == "aviso_enviado", Evento.criado_em >= desde).order_by(Evento.id)
            )
            pendentes = []
            for evento in eventos:
                espera = s.get(Espera, evento.espera_id)
                if espera and espera.status == "aguardando" and espera.ciente_em is None:
                    pendentes.append(
                        {
                            "tipo": "alerta",
                            "prefixo": espera.prefixo_avisado,
                            "espera_id": espera.id,
                            "parada_nome": self._parada_nome(espera.parada_id),
                            "paradas_ate": (evento.dados or {}).get("paradas_ate"),
                            "linha": espera.linha_avisada,
                            "em": iso(evento.criado_em),
                        }
                    )
            return pendentes

    # ------------------------------------------------------------------ Sonar Ponto e câmera

    def processar_deteccao(self, parada_id: str, dados: dict) -> int:
        if not self.paradas.existe(parada_id):
            log.warning("detecção de parada desconhecida: %s", parada_id)
            return 0
        parada = self.paradas.obter(parada_id)
        linha = normalizar_linha(dados.get("linha_lida"))
        confianca = min(1.0, max(0.0, _numero(dados.get("confianca"), 0.0)))
        tempo_parado = max(0.0, _numero(dados.get("tempo_parado_s"), 0.0))
        parou = dados.get("parou")
        parou = parou if isinstance(parou, bool) else tempo_parado >= LIMIAR_PAROU_S
        camera_ok = dados.get("camera_ok")
        camera_ok = camera_ok if isinstance(camera_ok, bool) else linha is not None
        registro = {
            "linha_lida": linha,
            "confianca": confianca,
            "tempo_parado_s": tempo_parado,
            "parou": parou,
            "camera_ok": camera_ok,
            "passou_em": dados.get("passou_em") if isinstance(dados.get("passou_em"), str) else None,
            "origem": str(dados.get("origem", "sonar_ponto"))[:20],
        }
        with self._transacao() as (s, saida):
            s.add(Evento(espera_id=None, parada_id=parada_id, tipo="deteccao", dados=registro, criado_em=agora()))
            saida.sse.append((f"parada:{parada_id}", {"tipo": "deteccao", "dados": registro, "em": iso(agora())}))
            ativas = self._ativas(s, parada_id)
            for espera in ativas:
                self._aplicar_deteccao(s, saida, espera, parada, linha, confianca, tempo_parado, parou, camera_ok, registro)
            return len(ativas)

    def _aplicar_deteccao(
        self,
        s: Session,
        saida: _Saida,
        e: Espera,
        parada: Parada,
        linha: str | None,
        confianca: float,
        tempo_parado: float,
        parou: bool,
        camera_ok: bool,
        registro: dict,
    ) -> None:
        if linha is None:
            self._emitir(
                s,
                saida,
                e,
                "onibus_chegando",
                "Um ônibus chegou ao ponto, mas sem confirmação visual da linha. Confirme com o motorista antes de embarcar.",
                e_o_seu=None,
                vibrar="curta",
                **registro,
            )
            return
        if linha not in e.linhas_alvo:
            self._emitir(
                s,
                saida,
                e,
                "onibus_chegando",
                f"Chegando agora: linha {linha}. Não é o seu.",
                e_o_seu=False,
                vibrar="dupla",
                **registro,
            )
            return
        destino = parada.destino(linha) or (e.ultima_previsao or {}).get("destino") or ""
        sentido = f", sentido {destino}" if destino else ""
        e.passagem_em = agora()
        e.passagem_linha = linha
        e.passagem_confianca = confianca
        e.passagem_tempo_parado_s = tempo_parado
        e.passagem_parou = parou
        e.passagem_camera_ok = camera_ok
        e.perguntou_embarque_em = None
        e.perguntou_parou_em = None
        if parou:
            duvida = " A leitura está incerta: confirme com o motorista." if confianca < CONFIANCA_MINIMA else ""
            self._emitir(
                s,
                saida,
                e,
                "onibus_chegando",
                f"Chegando agora: linha {linha}{sentido}. É o seu.{duvida}",
                e_o_seu=True,
                vibrar="longa",
                **registro,
            )
        else:
            self._emitir(
                s,
                saida,
                e,
                "onibus_passou_direto",
                f"A linha {linha}{sentido} passou sem parar. Se quiser registrar, toque em Não parou.",
                e_o_seu=True,
                vibrar="longa",
                **registro,
            )
            self._garantir_ocorrencia(s, e, status="aguardando_consentimento")

    def atualizar_dispositivo(self, tipo: str, ref: str, dados: dict) -> None:
        if not PADRAO_REF.fullmatch(ref):
            return
        online = dados.get("online", True) is not False
        instante = agora()
        with self._transacao() as (s, saida):
            chave = f"{tipo}:{ref}"
            dispositivo = s.get(Dispositivo, chave)
            estava_online = dispositivo.online if dispositivo else None
            if dispositivo is None:
                dispositivo = Dispositivo(id=chave, tipo=tipo, ref=ref)
                s.add(dispositivo)
            dispositivo.online = online
            dispositivo.ultimo_sinal_em = instante
            dispositivo.dados = {
                campo: dados[campo]
                for campo in ("estado", "rssi", "uptime_s", "fila", "camera_ok", "versao")
                if campo in dados
            }
            if estava_online and not online:
                self._avisar_queda(s, saida, dispositivo)
        DISPOSITIVO_ONLINE.labels(tipo, ref).set(1 if online else 0)
        DISPOSITIVO_ULTIMO_SINAL.labels(tipo, ref).set(instante.timestamp())

    def _avisar_queda(self, s: Session, saida: _Saida, dispositivo: Dispositivo) -> None:
        if dispositivo.tipo == "ponto":
            for espera in self._ativas(s, dispositivo.ref):
                self._emitir(
                    s,
                    saida,
                    espera,
                    "ponto_offline",
                    "O Sonar Ponto perdeu a conexão. Continuo com a previsão do Olho Vivo.",
                )
        elif dispositivo.tipo == "camera":
            for espera in self._ativas(s, dispositivo.ref):
                self._emitir(s, saida, espera, "sem_confirmacao_visual", FALA_SEM_CAMERA)

    def carregar_metricas_dispositivos(self) -> None:
        with self._leitura() as s:
            for dispositivo in s.scalars(select(Dispositivo)):
                DISPOSITIVO_ONLINE.labels(dispositivo.tipo, dispositivo.ref).set(1 if dispositivo.online else 0)
                DISPOSITIVO_ULTIMO_SINAL.labels(dispositivo.tipo, dispositivo.ref).set(
                    dispositivo.ultimo_sinal_em.timestamp()
                )

    def estado_parada(self, parada_id: str) -> dict:
        if not self.paradas.existe(parada_id):
            raise NaoEncontrado("parada não encontrada")
        with self._leitura() as s:
            ativas = self._ativas(s, parada_id)
            dispositivos = {
                d.tipo: {"online": d.online, "ultimo_sinal_em": iso(d.ultimo_sinal_em), **(d.dados or {})}
                for d in s.scalars(select(Dispositivo).where(Dispositivo.ref == parada_id))
            }
            return {
                "tipo": "estado",
                "parada": self.paradas.obter(parada_id).como_dict(),
                "esperas_ativas": len(ativas),
                "linhas_alvo": sorted({linha for e in ativas for linha in e.linhas_alvo}),
                "dispositivos": dispositivos,
                "em": iso(agora()),
            }

    def receber_mqtt(self, topico: str, dados: dict) -> None:
        partes = topico.split("/")
        if len(partes) < 4 or partes[0] != "sonar" or not PADRAO_REF.fullmatch(partes[2]):
            return
        grupo, ref, assunto = partes[1], partes[2], partes[3]
        if grupo == "parada":
            if assunto == "evento" and len(partes) == 4:
                self.processar_deteccao(ref, dados)
            elif assunto == "status" and len(partes) == 4:
                self.atualizar_dispositivo("ponto", ref, dados)
            elif assunto == "camera" and partes[4:] == ["status"]:
                self.atualizar_dispositivo("camera", ref, dados)
        elif grupo == "onibus" and len(partes) == 4:
            if assunto == "ciente":
                self.registrar_ciente(ref, dados)
            elif assunto == "status":
                self.atualizar_dispositivo("bordo", ref, dados)

    # ------------------------------------------------------------------ temporizadores

    def verificar_temporizadores(self) -> None:
        instante = agora()
        with self._transacao() as (s, saida):
            afetadas: set[str] = set()
            ativas = self._ativas(s)
            for espera in ativas:
                if instante >= espera.expira_em:
                    espera.status = "expirada"
                    espera.encerrado_em = instante
                    self._fechar_ocorrencia_pendente(s, espera, "anonima")
                    self._emitir(
                        s, saida, espera, "expirada", "A espera terminou por tempo. Se ainda precisar, comece de novo."
                    )
                    afetadas.add(espera.parada_id)
                    continue
                if espera.passagem_em and espera.passagem_parou and espera.embarque_em is None:
                    if espera.demo:
                        fator = 1 / max(self.cfg.demo_velocidade, 0.01)
                        primeira, segunda = 20 * fator, 45 * fator
                    else:
                        primeira, segunda = 45, 180
                    decorrido = (instante - espera.passagem_em).total_seconds()
                    if espera.perguntou_embarque_em is None and decorrido >= primeira:
                        espera.perguntou_embarque_em = instante
                        self._emitir(
                            s, saida, espera, "perguntar_embarque", "Você embarcou? Toque em Embarquei ou diga embarquei."
                        )
                    elif (
                        espera.perguntou_embarque_em is not None
                        and espera.perguntou_parou_em is None
                        and decorrido >= segunda
                    ):
                        espera.perguntou_parou_em = instante
                        self._emitir(
                            s,
                            saida,
                            espera,
                            "perguntar_parou",
                            f"A linha {espera.passagem_linha} passou e você não confirmou o embarque. "
                            "Ele parou? Se não parou, toque em Não parou.",
                        )
            for parada_id in afetadas:
                self._comandar_ponto(s, saida, parada_id)

            limite = instante - timedelta(seconds=90)  # o sinal de vida vem a cada 30 s
            sem_sinal = s.scalars(
                select(Dispositivo).where(Dispositivo.online.is_(True), Dispositivo.ultimo_sinal_em < limite)
            )
            for dispositivo in sem_sinal:
                dispositivo.online = False
                DISPOSITIVO_ONLINE.labels(dispositivo.tipo, dispositivo.ref).set(0)
                self._avisar_queda(s, saida, dispositivo)
            ESPERAS_ATIVAS.set(sum(1 for e in ativas if e.status == "aguardando"))

    # ------------------------------------------------------------------ robô de ocorrências (RPA)

    @staticmethod
    def ocorrencia_dict(ocorrencia: Ocorrencia) -> dict:
        return {
            "id": ocorrencia.id,
            "espera_id": ocorrencia.espera_id,
            "parada_id": ocorrencia.parada_id,
            "linha": ocorrencia.linha,
            "prefixo": ocorrencia.prefixo,
            "evidencias": ocorrencia.evidencias or {},
            "consentimento": ocorrencia.consentimento,
            "status": ocorrencia.status,
            "protocolo": ocorrencia.protocolo,
            "mensagem": ocorrencia.mensagem,
            "criado_em": iso(ocorrencia.criado_em),
            "atualizado_em": iso(ocorrencia.atualizado_em),
        }

    def listar_ocorrencias(self, status: str | None = None, limite: int = 100) -> list[dict]:
        with self._leitura() as s:
            consulta = select(Ocorrencia).order_by(Ocorrencia.id)
            if status:
                consulta = consulta.where(Ocorrencia.status == status)
            return [self.ocorrencia_dict(o) for o in s.scalars(consulta.limit(limite))]

    def atualizar_ocorrencia(
        self, ocorrencia_id: int, status: str, protocolo: str | None = None, mensagem: str | None = None
    ) -> dict:
        if status not in STATUS_DO_ROBO:
            raise ValueError(f"status inválido: {status}")
        with self._transacao() as (s, saida):
            ocorrencia = s.get(Ocorrencia, ocorrencia_id)
            if ocorrencia is None:
                raise NaoEncontrado("ocorrência não encontrada")
            ocorrencia.status = status
            if protocolo:
                ocorrencia.protocolo = protocolo
            if mensagem is not None:
                ocorrencia.mensagem = mensagem
            ocorrencia.atualizado_em = agora()
            espera = s.get(Espera, ocorrencia.espera_id)
            if espera is not None and status == "enviada" and ocorrencia.protocolo:
                self._emitir(
                    s,
                    saida,
                    espera,
                    "ocorrencia_protocolo",
                    f"Sua reclamação foi registrada com o protocolo {ocorrencia.protocolo}.",
                    protocolo=ocorrencia.protocolo,
                    ocorrencia_id=ocorrencia.id,
                )
            elif espera is not None and status == "inconclusiva":
                self._emitir(
                    s,
                    saida,
                    espera,
                    "ocorrencia_inconclusiva",
                    "Não deu para confirmar a ocorrência com as evidências do ponto. Ela fica no relatório anônimo.",
                    ocorrencia_id=ocorrencia.id,
                )
            return self.ocorrencia_dict(ocorrencia)

    # ------------------------------------------------------------------ painel da cidade

    def indicadores(self, dias: int = 30, incluir_demo: bool = True) -> dict:
        desde = agora() - timedelta(days=dias)
        with self._leitura() as s:
            consulta = select(Espera).where(Espera.criado_em >= desde)
            if not incluir_demo:
                consulta = consulta.where(Espera.demo.is_(False))
            esperas = list(s.scalars(consulta))
            ids = {e.id for e in esperas}
            ocorrencias = [o for o in s.scalars(select(Ocorrencia)) if o.espera_id in ids]
            dispositivos = [
                {"tipo": d.tipo, "id": d.ref, "online": d.online, "ultimo_sinal_em": iso(d.ultimo_sinal_em)}
                for d in s.scalars(select(Dispositivo).order_by(Dispositivo.id))
            ]

        def linha_de(e: Espera) -> str:
            return e.passagem_linha or e.linha_avisada or (e.linhas_alvo[0] if e.linhas_alvo else "?")

        por_linha: dict[str, Counter] = defaultdict(Counter)
        tempos = []
        for e in esperas:
            contagem = por_linha[linha_de(e)]
            contagem["esperas"] += 1
            contagem["avisos"] += bool(e.aviso_enviado_em)
            contagem["cientes"] += bool(e.ciente_em)
            contagem["embarques"] += e.status == "embarcou"
            contagem["nao_parou"] += e.status == "nao_parou"
            if e.embarque_em:
                tempos.append((e.embarque_em - e.criado_em).total_seconds() / 60)

        total = len(esperas)
        avisos = sum(1 for e in esperas if e.aviso_enviado_em)
        cientes = sum(1 for e in esperas if e.ciente_em)
        nao_parou = sum(1 for e in esperas if e.status == "nao_parou")
        return {
            "periodo_dias": dias,
            "incluir_demo": incluir_demo,
            "esperas": total,
            "avisos_enviados": avisos,
            "avisos_ciente": cientes,
            "taxa_ciente": round(cientes / avisos, 3) if avisos else None,
            "embarques": sum(1 for e in esperas if e.status == "embarcou"),
            "embarques_validados_camera": sum(1 for e in esperas if e.validado_por_camera),
            "nao_parou": nao_parou,
            "nao_parou_por_100_esperas": round(100 * nao_parou / total, 1) if total else None,
            "tempo_medio_espera_min": round(sum(tempos) / len(tempos), 1) if tempos else None,
            "ocorrencias_por_status": dict(Counter(o.status for o in ocorrencias)),
            "por_linha": [
                {"linha": linha, **dict(contagem)}
                for linha, contagem in sorted(por_linha.items(), key=lambda item: -item[1]["esperas"])
            ],
            "dispositivos": dispositivos,
            "gerado_em": iso(agora()),
        }
