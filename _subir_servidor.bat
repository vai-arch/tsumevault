@echo off
echo Subiendo tsumevault_server.py al servidor...

scp "%~dp0server\ai_engines.py" root@46.225.97.185:/opt/tsumevault/
scp "%~dp0server\ai_engines.json" root@46.225.97.185:/opt/tsumevault/
scp "%~dp0server\fuego_tv.cfg" root@46.225.97.185:/opt/tsumevault/
scp "%~dp0server\tsumevault_server.py" root@46.225.97.185:/opt/tsumevault/
scp "%~dp0server\Caddyfile" root@46.225.97.185:/opt/tsumevault/
echo Reiniciando servicio...

ssh root@46.225.97.185 "sudo systemctl reload caddy"
ssh root@46.225.97.185 "systemctl restart tsumevault"


echo Listo.
pause
