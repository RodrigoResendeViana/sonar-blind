# syntax=docker/dockerfile:1
# Imagem "web": o PWA compilado servido pelo Caddy, que também faz o HTTPS e o proxy da API.
# A configuração (Caddyfile) vem do repositório, montada pelo docker-compose.

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM caddy:2-alpine
LABEL org.opencontainers.image.title="sonar-web" \
      org.opencontainers.image.description="PWA do Sonar servido pelo Caddy (FIAP Global Solution 2026.2)"
# Roda sem root e com no-new-privileges. Por isso o binário perde a capability de arquivo
# (com no-new-privileges ela impediria o exec); as portas 80 e 443 abrem pelo sysctl
# net.ipv4.ip_unprivileged_port_start=0 definido no docker-compose.yml.
RUN apk add --no-cache libcap \
 && setcap -r /usr/bin/caddy \
 && apk del libcap \
 && addgroup -S -g 10001 sonar \
 && adduser -S -D -H -u 10001 -G sonar sonar \
 && mkdir -p /data /config \
 && chown -R sonar:sonar /data /config
COPY --from=build /app/dist /srv
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["wget", "-q", "--spider", "http://127.0.0.1/"]
