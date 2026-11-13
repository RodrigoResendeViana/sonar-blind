#!/usr/bin/env bash
# Publica o Sonar na EC2. O pipeline chama este script pelo AWS SSM (como root), depois de
# fazer checkout do commit em /opt/sonar/repo. Ninguém entra no servidor por SSH.
#
# Uso: deploy.sh <tag-da-imagem>
#
# Lê os segredos do Parameter Store (/sonar/...), gera o .env, as senhas e a ACL do Mosquitto
# e o token do Telegram, sobe o compose e copia o certificado do Caddy para o MQTT (porta 8883).
set -euo pipefail

TAG="${1:?uso: deploy.sh <tag-da-imagem>}"
export AWS_DEFAULT_REGION="${AWS_REGION:-us-east-1}"
COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEGREDOS=/opt/sonar/segredos
REGISTRO="${SONAR_REGISTRY:-ghcr.io/rodrigoresendeviana}"
IMAGEM_MOSQUITTO="eclipse-mosquitto:2"
UID_MOSQUITTO=1883
UID_NOBODY=65534

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
install -d -m 750 -o "$UID_MOSQUITTO" -g "$UID_MOSQUITTO" "$SEGREDOS/mosquitto" "$SEGREDOS/mosquitto/certs"
install -d -m 750 -o "$UID_NOBODY" -g "$UID_NOBODY" "$SEGREDOS/alertmanager"

log "lendo parâmetros do Parameter Store"
DOMINIO="$(parametro /sonar/deploy/dominio)"
DB_SENHA="$(parametro /sonar/db/senha)"
TOKEN_SERVICO="$(parametro /sonar/api/token-servico)"
SAL_HASH="$(parametro /sonar/api/sal-hash)"
OLHOVIVO_TOKEN="$(parametro_opcional /sonar/olhovivo/token)"
IA_URL="$(parametro_opcional /sonar/ia/url)"
IA_MODELO="$(parametro_opcional /sonar/ia/modelo)"
PERFIS="$(parametro_opcional /sonar/compose/perfis)"
GHCR_USUARIO="$(parametro_opcional /sonar/ghcr/usuario)"
GRAFANA_SENHA="$(parametro /sonar/grafana/senha)"
N8N_CHAVE="$(parametro_opcional /sonar/n8n/chave)"
TELEGRAM_TOKEN="$(parametro_opcional /sonar/telegram/token)"
TELEGRAM_CHAT_ID="$(parametro_opcional /sonar/telegram/chat-id)"
GHCR_TOKEN="$(parametro_opcional /sonar/ghcr/token)"
[ -n "$OLHOVIVO_TOKEN" ] || log "AVISO: /sonar/olhovivo/token não existe; a API sobe só com a demonstração"

# IA generativa e RPA vêm ligados: sem /sonar/compose/perfis, sobem os perfis ia e rpa.
# Para desligar os dois, grave o valor "nenhum" nesse parâmetro.
case "$PERFIS" in
  '') PERFIS="ia,rpa" ;;
  nenhum) PERFIS="" ;;
esac
tem_perfil() { [[ ",$PERFIS," == *",$1,"* ]]; }
if tem_perfil ia && [ -z "$IA_URL" ]; then
  IA_URL="http://ia:8100"
fi
RPA_WEBHOOK=""
if tem_perfil rpa; then
  RPA_WEBHOOK="http://n8n:5678/webhook/sonar-ocorrencia"
  if [ -z "$N8N_CHAVE" ]; then
    # sem o terraform apply que cria /sonar/n8n/chave: gera uma chave e guarda no disco da EC2
    # (precisa ser sempre a mesma, porque cifra as credenciais que o n8n guarda)
    if [ ! -s "$SEGREDOS/n8n_chave" ]; then
      head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 40 >"$SEGREDOS/n8n_chave"
      chmod 600 "$SEGREDOS/n8n_chave"
    fi
    N8N_CHAVE="$(cat "$SEGREDOS/n8n_chave")"
  fi
fi
log "perfis extras: ${PERFIS:-nenhum}"

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
      printf 'user %s\ntopic write sonar/parada/%s/visao\ntopic write sonar/parada/%s/mira\ntopic write sonar/parada/%s/camera/status\ntopic read sonar/parada/%s/cmd\n\n' \
        "$usuario" "$p" "$p" "$p" "$p" ;;
    braco-*)
      p="${usuario#braco-}"
      printf 'user %s\ntopic read sonar/parada/%s/mira\ntopic read sonar/parada/%s/cmd\ntopic write sonar/parada/%s/braco/status\n\n' \
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

log "configurando o Telegram dos alertas"
if [ -n "$TELEGRAM_TOKEN" ]; then
  printf '%s' "$TELEGRAM_TOKEN" >"$TMP/telegram_token"
  install -m 600 -o "$UID_NOBODY" -g "$UID_NOBODY" "$TMP/telegram_token" "$SEGREDOS/alertmanager/telegram_token"
else
  rm -f "$SEGREDOS/alertmanager/telegram_token"
  log "AVISO: /sonar/telegram/token não existe; os alertas não vão para o Telegram"
fi
case "$TELEGRAM_CHAT_ID" in ''|-[0-9]*|[0-9]*) ;; *) falhar "/sonar/telegram/chat-id precisa ser um número" ;; esac

escrever_env() {
  local conf_mqtt="$1"
  for par in "DOMINIO:$DOMINIO" "OLHOVIVO:$OLHOVIVO_TOKEN" "IA_URL:$IA_URL" "IA_MODELO:$IA_MODELO" "PERFIS:$PERFIS" "N8N:$N8N_CHAVE"; do
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
SONAR_RPA_WEBHOOK_URL='$RPA_WEBHOOK'
SONAR_IA_MODELO='${IA_MODELO:-qwen2.5:3b}'
SONAR_GRAFANA_PASSWORD='$GRAFANA_SENHA'
SONAR_N8N_CHAVE='$N8N_CHAVE'
SONAR_TELEGRAM_CHAT_ID='$TELEGRAM_CHAT_ID'
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

if tem_perfil rpa && [ -d "$COMPOSE_DIR/../../rpa/n8n" ]; then
  # o repositório é a fonte da verdade dos fluxos: mudou no editor do n8n, exporte para rpa/n8n
  log "importando e publicando os fluxos do n8n (rpa/n8n)"
  for _ in $(seq 1 30); do
    docker compose exec -T n8n node -e \
      "fetch('http://127.0.0.1:5678/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))" \
      >/dev/null 2>&1 && break
    sleep 2
  done
  N8N_OK=1
  docker compose exec -T n8n n8n unpublish:workflow --all >/dev/null 2>&1 || true
  docker compose exec -T n8n n8n import:workflow --separate --input=/workflows >/dev/null 2>&1 || N8N_OK=0
  for arquivo in "$COMPOSE_DIR"/../../rpa/n8n/*.json; do
    ID="$(sed -n 's/^  "id": "\([A-Za-z0-9]*\)",$/\1/p' "$arquivo" | head -n 1)"
    [ -n "$ID" ] || continue
    docker compose exec -T n8n n8n publish:workflow --id="$ID" >/dev/null 2>&1 ||
      docker compose exec -T n8n n8n update:workflow --id="$ID" --active=true >/dev/null 2>&1 || N8N_OK=0
  done
  docker compose restart n8n >/dev/null
  [ "$N8N_OK" = 1 ] || log "AVISO: não consegui importar/publicar algum fluxo do n8n; publique pelo editor (rpa/README.md)"
fi

if tem_perfil ia; then
  MODELO="${IA_MODELO:-qwen2.5:3b}"
  log "baixando o modelo $MODELO no Ollama (a primeira vez demora alguns minutos)"
  docker compose exec -T ollama ollama pull "$MODELO" >/dev/null
  log "carregando o modelo na memória (a primeira pergunta não espera o carregamento)"
  timeout 180 docker compose exec -T ollama ollama run "$MODELO" "Responda só: ok" >/dev/null 2>&1 ||
    log "AVISO: o modelo demorou para carregar; a API responde por regras até ele ficar pronto"
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
