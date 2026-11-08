"""Banco de dados: tabelas do MVP.

Nenhuma tabela guarda nome, telefone ou localização do usuário. O usuário aparece
só como hash SHA-256 com sal (LGPD), e a parada é o nível máximo de localização.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator


def agora() -> datetime:
    return datetime.now(timezone.utc)


def iso(valor: datetime | None) -> str | None:
    return valor.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if valor else None


class UTCDateTime(TypeDecorator):
    """Guarda sempre em UTC e devolve datetime com fuso, inclusive no SQLite."""

    impl = DateTime
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(timezone=True)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


class Espera(Base):
    __tablename__ = "esperas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    parada_id: Mapped[str] = mapped_column(String(64), index=True)
    linhas_alvo: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), index=True, default="aguardando")
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    origem: Mapped[str] = mapped_column(String(8), default="toque")
    usuario_hash: Mapped[str | None] = mapped_column(String(64))
    criado_em: Mapped[datetime] = mapped_column(UTCDateTime(), default=agora)
    expira_em: Mapped[datetime] = mapped_column(UTCDateTime())
    encerrado_em: Mapped[datetime | None] = mapped_column(UTCDateTime())

    ultima_previsao: Mapped[dict | None] = mapped_column(JSON)

    aviso_enviado_em: Mapped[datetime | None] = mapped_column(UTCDateTime())
    prefixo_avisado: Mapped[str | None] = mapped_column(String(16))
    linha_avisada: Mapped[str | None] = mapped_column(String(16))
    ciente_em: Mapped[datetime | None] = mapped_column(UTCDateTime())

    passagem_em: Mapped[datetime | None] = mapped_column(UTCDateTime())
    passagem_linha: Mapped[str | None] = mapped_column(String(16))
    passagem_confianca: Mapped[float | None] = mapped_column(Float)
    passagem_tempo_parado_s: Mapped[float | None] = mapped_column(Float)
    passagem_parou: Mapped[bool | None] = mapped_column(Boolean)
    passagem_camera_ok: Mapped[bool | None] = mapped_column(Boolean)

    perguntou_embarque_em: Mapped[datetime | None] = mapped_column(UTCDateTime())
    perguntou_parou_em: Mapped[datetime | None] = mapped_column(UTCDateTime())

    embarque_em: Mapped[datetime | None] = mapped_column(UTCDateTime())
    embarque_origem: Mapped[str | None] = mapped_column(String(8))
    validado_por_camera: Mapped[bool | None] = mapped_column(Boolean)


class Evento(Base):
    """Log de tudo o que acontece. Vira o histórico do SSE e a fonte do Big Data."""

    __tablename__ = "eventos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    espera_id: Mapped[str | None] = mapped_column(String(36), index=True)
    parada_id: Mapped[str | None] = mapped_column(String(64), index=True)
    tipo: Mapped[str] = mapped_column(String(40))
    fala: Mapped[str | None] = mapped_column(Text)
    dados: Mapped[dict] = mapped_column(JSON, default=dict)
    criado_em: Mapped[datetime] = mapped_column(UTCDateTime(), default=agora, index=True)


class Ocorrencia(Base):
    """Ônibus que não parou. O robô de RPA lê as pendentes e devolve o protocolo."""

    __tablename__ = "ocorrencias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    espera_id: Mapped[str] = mapped_column(ForeignKey("esperas.id"), index=True)
    parada_id: Mapped[str] = mapped_column(String(64))
    linha: Mapped[str | None] = mapped_column(String(16))
    prefixo: Mapped[str | None] = mapped_column(String(16))
    evidencias: Mapped[dict] = mapped_column(JSON, default=dict)
    consentimento: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), index=True)
    protocolo: Mapped[str | None] = mapped_column(String(64))
    mensagem: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(UTCDateTime(), default=agora)
    atualizado_em: Mapped[datetime] = mapped_column(UTCDateTime(), default=agora)


class Dispositivo(Base):
    """Sonar Ponto, câmera do ponto e Sonar Bordo, com o último sinal de vida."""

    __tablename__ = "dispositivos"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tipo: Mapped[str] = mapped_column(String(16))
    ref: Mapped[str] = mapped_column(String(64))
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    ultimo_sinal_em: Mapped[datetime] = mapped_column(UTCDateTime(), default=agora)
    dados: Mapped[dict] = mapped_column(JSON, default=dict)


def criar_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        argumentos = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url or url.endswith("://"):
            argumentos["poolclass"] = StaticPool
        return create_engine(url, **argumentos)
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)
