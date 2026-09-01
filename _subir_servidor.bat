@echo off
echo Subiendo tsumevault_server.py al servidor...

scp "%~dp0tsumevault_server.py" root@46.225.97.185:/opt/tsumevault/
scp "%~dp0Caddyfile" root@46.225.97.185:/opt/tsumevault/
scp "%~dp0player\recorded.json" root@46.225.97.185:/opt/tsumevault/player

echo Reiniciando servicio...

ssh root@46.225.97.185 "sudo systemctl reload caddy"
ssh root@46.225.97.185 "systemctl restart tsumevault"


echo Listo.
pause
