@echo off
setlocal

set HOST=root@46.225.97.185
set SSH_OPTS=-o ServerAliveInterval=20 -o ServerAliveCountMax=12

echo Subiendo Caddyfile a /opt/tsumevault/Caddyfile...
scp %SSH_OPTS% "%~dp0Caddyfile" %HOST%:/opt/tsumevault/Caddyfile
if errorlevel 1 (
  echo.
  echo ERROR subiendo Caddyfile.
  pause
  exit /b 1
)

echo Enlazando /etc/caddy/Caddyfile -^> /opt/tsumevault/Caddyfile...
ssh %SSH_OPTS% %HOST% "ln -sf /opt/tsumevault/Caddyfile /etc/caddy/Caddyfile"
if errorlevel 1 (
  echo.
  echo ERROR creando el enlace simbolico.
  pause
  exit /b 1
)

echo Validando la configuracion antes de recargar...
ssh %SSH_OPTS% %HOST% "caddy validate --config /etc/caddy/Caddyfile"
if errorlevel 1 (
  echo.
  echo ======================================================
  echo   La configuracion de Caddy NO es valida. NO se recargo.
  echo   Revisa el Caddyfile antes de volver a intentarlo.
  echo ======================================================
  pause
  exit /b 1
)

echo Recargando Caddy ^(sin cortar el servicio^)...
ssh %SSH_OPTS% %HOST% "systemctl reload caddy"
if errorlevel 1 (
  echo.
  echo ERROR recargando caddy. Revisa 'systemctl status caddy' en el servidor.
  pause
  exit /b 1
)

echo.
echo Listo. Caddyfile desplegado, enlazado y recargado.
pause
