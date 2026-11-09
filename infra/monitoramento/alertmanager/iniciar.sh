#!/bin/sh
# Monta a configuração do Alertmanager. Com o Telegram configurado no Parameter Store,
# os alertas vão para o bot; sem ele, ficam só registrados.
set -e
if [ -n "$TELEGRAM_CHAT_ID" ] && [ -s /run/segredos/telegram_token ]; then
  sed "s/__TELEGRAM_CHAT_ID__/$TELEGRAM_CHAT_ID/" /etc/alertmanager/alertmanager.yml.tmpl > /tmp/alertmanager.yml
else
  echo "Telegram não configurado: os alertas não serão enviados"
  cp /etc/alertmanager/sem-telegram.yml /tmp/alertmanager.yml
fi
exec /bin/alertmanager --config.file=/tmp/alertmanager.yml --storage.path=/alertmanager
