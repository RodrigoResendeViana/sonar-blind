#!/usr/bin/env bash
# Publica o Sonar na EC2. O pipeline chama este script pelo AWS SSM (como root), depois de
# fazer checkout do commit em /opt/sonar/repo. Ninguém entra no servidor por SSH.
#
# Uso: deploy.sh <tag-da-imagem>
#
# Lê os segredos do Parameter Store (/sonar/...), gera o .env, as senhas e a ACL do Mosquitto
# e a senha das métricas, sobe o compose e copia o certificado do Caddy para o MQTT (porta 8883).
set -euo pipefail

TAG="${1:?uso: deploy.sh <tag-da-imagem>}"
export AWS_DEFAULT_REGION="${AWS_REGION:-us-east-1}"
COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEGREDOS=/opt/sonar/segredos
REGISTRO="${SONAR_REGISTRY:-ghcr.io/rodrigoresendeviana}"
IMAGEM_MOSQUITTO="eclipse-mosquitto:2"
UID_CADDY=10001
UID_MOSQUITTO=1883

log() { printf '[deploy %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
falhar() { log "ERRO: $*"; exit 1; }

parametro() {
  aws ssm get-parameter --name "$1" --with-decryption --query Parameter.Value --output text
}
parametro_opcional() {
  aws ssm get-parameter --name "$1" --with-decryption --query Parameter.Value --output text 2>/dev/null || true
}
# valores do .env vão entre aspas simples (o compose não interpola); aspas simples são proibidas
seguro() {
  case "$2" in *"'"* | *$'\n'*) falhar "o parâmetro $1 tem caractere não suportado" ;; esac
}

umask 077
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
install -d -m 755 /opt/sonar "$SEGREDOS"
install -d -m 750 -o "$UID_CADDY" -g "$UID_CADDY" "$SEGREDOS/caddy"
install -d -m 750 -o "$UID_MOSQUITTO" -g "$UID_MOSQUITTO" "$SEGREDOS/mosquitto" "$SEGREDOS/mosquitto/certs"

log "lendo parâmetros do Parameter Store"
DOMINIO="$(parametro /sonar/deploy/dominio)"
DB_SENHA="$(parametro /sonar/db/senha)"
TOKEN_SERVICO="$(parametro /sonar/api/token-servico)"
SAL_HASH="$(parametro /sonar/api/sal-hash)"
METRICAS_SENHA="$(parametro /sonar/metricas/senha)"
OLHOVIVO_TOKEN="$(parametro_opcional /sonar/olhovivo/token)"
IA_URL="$(parametro_opcional /sonar/ia/url)"
PERFIS="$(parametro_opcional /sonar/compose/perfis)"
GHCR_USUARIO="$(parametro_opcional /sonar/ghcr/usuario)"
GHCR_TOKEN="$(parametro_opcional /sonar/ghcr/token)"
[ -n "$OLHOVIVO_TOKEN" ] || log "AVISO: /sonar/olhovivo/token não existe; a API sobe só com a demonstração"

log "gerando usuários e ACL do Mosquitto"
aws ssm get-parameters-by-path --path /sonar/mqtt/usuarios --with-decryption \
  --query 'Parameters[].[Name,Value]' --output text >"$TMP/usuarios.tsv"
: >"$TMP/passwd"
: >"$TMP/acl"
MQTT_API_SENHA=""
while IFS=$'\t' read -r nome senha; do
  [ -n "$nome" ] || continue
  usuario="${nome##*/}"
  case "$usuario" in
    sonar-api)
      MQTT_API_SENHA="$senha"
      printf 'user %s\ntopic readwrite sonar/#\n\n' "$usuario" ;;
    ponto-*)
      p="${usuario#ponto-}"
      printf 'user %s\ntopic write sonar/parada/%s/evento\ntopic write sonar/parada/%s/status\ntopic read sonar/parada/%s/cmd\ntopic read sonar/parada/%s/visao\ntopic read sonar/parada/%s/camera/status\n\n' \
        "$usuario" "$p" "$p" "$p" "$p" "$p" ;;
    camera-*)
      p="${usuario#camera-}"
      printf 'user %s\ntopic write sonar/parada/%s/visao\ntopic write sonar/parada/%s/camera/status\ntopic read sonar/parada/%s/cmd\n\n' \
        "$usuario" "$p" "$p" "$p" ;;
    bordo-*)
      o="${usuario#bordo-}"
      printf 'user %s\ntopic read sonar/onibus/%s/alerta\ntopic write sonar/onibus/%s/ciente\ntopic write sonar/onibus/%s/status\n\n' \
        "$usuario" "$o" "$o" "$o" ;;
    *)
      log "usuário MQTT ignorado (prefixo desconhecido): $usuario"
      continue ;;
  esac >>"$TMP/acl"
  printf '%s:%s\n' "$usuario" "$senha" >>"$TMP/passwd"
done <"$TMP/usuarios.tsv"
[ -n "$MQTT_API_SENHA" ] || falhar "falta o parâmetro /sonar/mqtt/usuarios/sonar-api"
docker run --rm --user 0 --network none -v "$TMP:/w" "$IMAGEM_MOSQUITTO" mosquitto_passwd -U /w/passwd
install -m 600 -o "$UID_MOSQUITTO" -g "$UID_MOSQUITTO" "$TMP/passwd" "$SEGREDOS/mosquitto/passwd"
install -m 600 -o "$UID_MOSQUITTO" -g "$UID_MOSQUITTO" "$TMP/acl" "$SEGREDOS/mosquitto/acl"

log "gerando a senha das métricas (bcrypt)"
HASH="$(printf '%s' "$METRICAS_SENHA" | htpasswd -niBC 10 prometheus | cut -d: -f2-)"
printf 'basic_auth {\n\tprometheus %s\n}\n' "$HASH" >"$TMP/metrics_auth.caddy"
install -m 640 -o "$UID_CADDY" -g "$UID_CADDY" "$TMP/metrics_auth.caddy" "$SEGREDOS/caddy/metrics_auth.caddy"

escrever_env() {
  local conf_mqtt="$1"
  for par in "DOMINIO:$DOMINIO" "OLHOVIVO:$OLHOVIVO_TOKEN" "IA_URL:$IA_URL" "PERFIS:$PERFIS"; do
    seguro "${par%%:*}" "${par#*:}"
  done
  cat >"$COMPOSE_DIR/.env" <<EOF
SONAR_IMAGE_TAG='$TAG'
SONAR_REGISTRY='$REGISTRO'
SONAR_SITE_ADDRESS='$DOMINIO'
SONAR_SEGREDOS_DIR='$SEGREDOS'
SONAR_MQTT_CONF='$conf_mqtt'
SONAR_DB_PASSWORD='$DB_SENHA'
SONAR_MQTT_API_PASSWORD='$MQTT_API_SENHA'
SONAR_OLHOVIVO_TOKEN='$OLHOVIVO_TOKEN'
SONAR_TOKEN_SERVICO='$TOKEN_SERVICO'
SONAR_SAL_HASH='$SAL_HASH'
SONAR_IA_URL='$IA_URL'
COMPOSE_PROFILES='producao${PERFIS:+,$PERFIS}'
EOF
  chmod 600 "$COMPOSE_DIR/.env"
}

if [ -s "$SEGREDOS/mosquitto/certs/fullchain.pem" ]; then
  CONF_MQTT=mosquitto.conf
else
  CONF_MQTT=mosquitto.semtls.conf
fi
escrever_env "$CONF_MQTT"

if [ -n "$GHCR_TOKEN" ]; then
  log "login no GHCR (imagens privadas)"
  printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u "${GHCR_USUARIO:-sonar}" --password-stdin >/dev/null
fi

cd "$COMPOSE_DIR"
log "baixando as imagens $TAG"
docker compose pull --quiet
log "subindo os serviços"
docker compose up -d --remove-orphans

log "copiando o certificado do Caddy para o MQTT"
DIR_CERT="/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/$DOMINIO"
for _ in $(seq 1 24); do
  if docker compose cp "web:$DIR_CERT/$DOMINIO.crt" "$TMP/fullchain.pem" >/dev/null 2>&1 &&
    docker compose cp "web:$DIR_CERT/$DOMINIO.key" "$TMP/privkey.pem" >/dev/null 2>&1; then
    break
  fi
  sleep 5
done
NOVA_CONF="$CONF_MQTT"
CERT_MUDOU=0
if [ -s "$TMP/fullchain.pem" ] && [ -s "$TMP/privkey.pem" ]; then
  cmp -s "$TMP/fullchain.pem" "$SEGREDOS/mosquitto/certs/fullchain.pem" || CERT_MUDOU=1
  install -m 644 -o "$UID_MOSQUITTO" -g "$UID_MOSQUITTO" "$TMP/fullchain.pem" "$SEGREDOS/mosquitto/certs/fullchain.pem"
  install -m 600 -o "$UID_MOSQUITTO" -g "$UID_MOSQUITTO" "$TMP/privkey.pem" "$SEGREDOS/mosquitto/certs/privkey.pem"
  NOVA_CONF=mosquitto.conf
else
  log "AVISO: ainda não há certificado para $DOMINIO (o registro A já aponta para este IP?)."
  log "       O MQTT fica só na rede interna; rode o deploy de novo depois que o DNS propagar."
fi
if [ "$NOVA_CONF" != "$CONF_MQTT" ]; then
  escrever_env "$NOVA_CONF"
  docker compose up -d mqtt
elif [ "$CERT_MUDOU" = 1 ]; then
  docker compose restart mqtt
fi

if [[ ",$PERFIS," == *",ia,"* ]]; then
  MODELO="$(parametro_opcional /sonar/ia/modelo)"
  if [ -n "$MODELO" ]; then
    log "baixando o modelo $MODELO no Ollama"
    docker compose exec -T ollama ollama pull "$MODELO"
  fi
fi

log "conferindo a API"
for _ in $(seq 1 40); do
  if docker compose exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=3)" >/dev/null 2>&1; then
    docker compose ps --format 'table {{.Service}}\t{{.Status}}'
    docker image prune -af --filter "until=168h" >/dev/null || true
    log "deploy de $TAG concluído"
    exit 0
  fi
  sleep 3
done
docker compose ps
docker compose logs --tail 60 api
falhar "a API não ficou pronta"
