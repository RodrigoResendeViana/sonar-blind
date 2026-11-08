# syntax=docker/dockerfile:1
# Imagem da API: multi-stage, usuário não root, nenhum segredo dentro.
# Os segredos chegam por variáveis de ambiente, geradas no deploy a partir do Parameter Store.

FROM python:3.13-slim AS dependencias
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements.txt .
RUN python -m venv /venv && /venv/bin/pip install --require-virtualenv -r requirements.txt

FROM python:3.13-slim
LABEL org.opencontainers.image.title="sonar-api" \
      org.opencontainers.image.description="API do Sonar (FIAP Global Solution 2026.2)"
ENV PATH=/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd --system --gid 10001 sonar \
 && useradd --system --uid 10001 --gid sonar --home-dir /app --shell /usr/sbin/nologin sonar
COPY --from=dependencias /venv /venv
WORKDIR /app
COPY sonar_api ./sonar_api
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]
# --proxy-headers: o IP real do cliente vem do Caddy (único caminho até a API)
CMD ["uvicorn", "--factory", "sonar_api.main:create_app", "--host", "0.0.0.0", "--port", "8000", \
     "--root-path", "/api", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
