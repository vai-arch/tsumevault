#!/bin/bash
# Healthcheck para tsumevault.service
# Si el puerto 3002 no responde (conexión rechazada o timeout), reinicia el servicio.
# Nota: un 404 cuenta como "vivo" — solo nos importa si curl puede conectar.

LOG="/var/log/tsumevault_healthcheck.log"

if ! curl -s -o /dev/null --max-time 5 http://localhost:3002/; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - tsumevault no responde, reiniciando" >> "$LOG"
    systemctl restart tsumevault
fi
