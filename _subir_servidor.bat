@echo off
echo Subiendo tsumevault_server.py al servidor...

scp "%~dp0tsumevault_server.py" root@46.225.97.185:/opt/tsumevault/

echo Reiniciando servicio...
ssh root@46.225.97.185 "systemctl restart tsumevault"

echo Listo.
pause
