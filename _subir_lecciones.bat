@echo off
setlocal

set HOST=root@46.225.97.185
set SSH_OPTS=-o ServerAliveInterval=20 -o ServerAliveCountMax=12

echo Creando carpeta player\ en el servidor si no existe...
ssh %SSH_OPTS% %HOST% "mkdir -p /opt/tsumevault/player"
if errorlevel 1 (
  echo.
  echo ERROR: no se pudo conectar / crear la carpeta remota. Abortando.
  pause
  exit /b 1
)

echo Subiendo manifest (all_lessons.json)...
scp %SSH_OPTS% "%~dp0player\all_lessons.json" %HOST%:/opt/tsumevault/player/
if errorlevel 1 (
  echo.
  echo ERROR subiendo all_lessons.json.
  pause
  exit /b 1
)

echo Subiendo lecciones (sgf/json/ogg)... esto puede tardar, son varios GB.
echo Si se corta la conexion, simplemente vuelve a lanzar este script: scp sobreescribe sin problema.
scp -r %SSH_OPTS% "%~dp0player\lessons" %HOST%:/opt/tsumevault/player/
if errorlevel 1 (
  echo.
  echo ======================================================
  echo   FALLO la subida de lecciones ^(conexion cortada?^).
  echo   Vuelve a lanzar este script para reintentar.
  echo ======================================================
  pause
  exit /b 1
)

echo.
echo Listo de verdad esta vez. NOTA: studied.json y recorded.json NO se suben ^(uso solo local^).
pause
