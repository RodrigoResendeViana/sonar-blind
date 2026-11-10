# syntax=docker/dockerfile:1
# Imagem do agente de IA: multi-stage, usuário não root, nenhum segredo dentro.
# Os segredos chegam por variáveis de ambiente, geradas no deploy a partir do Parameter Store.

FROM python:3.13-slim AS dependencias
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements.txt .
# o pip sai da venv: ele traz cópias próprias de urllib3, msgpack e setuptools que o Trivy aponta
RUN python -m venv /venv && /venv/bin/pip install --require-virtualenv -r requirements.txt \
 && /venv/bin/python -m pip uninstall -y pip

FROM python:3.13-slim
# correções de segurança do Debian que ainda não entraram na imagem base; sem pip na imagem final
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/* \
 && python -m pip uninstall -y pip
LABEL org.opencontainers.image.title="sonar-ia" \
      org.opencontainers.image.description="Agente de IA do Sonar (FIAP Global Solution 2026.2)"
ENV PATH=/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd --system --gid 10001 sonar \
 && useradd --system --uid 10001 --gid sonar --home-dir /app --shell /usr/sbin/nologin sonar
COPY --from=dependencias /venv /venv
WORKDIR /app
COPY sonar_ia ./sonar_ia
USER 10001:10001
EXPOSE 8100
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/healthz', timeout=4)"]
CMD ["uvicorn", "sonar_ia.main:app", "--host", "0.0.0.0", "--port", "8100", "--no-server-header"]
