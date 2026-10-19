@echo off
setlocal

rem ------------------------------------------------------------------
rem  Sube SOLO los <id>.sgf y <id>.json regenerados con --board-only.
rem  Origen por defecto: board_out\lessons (junto a este .bat), generado con
rem    python awesome_to_player.py lessons.json --board-only --ids RUTA ^
rem        --published-dir RUTA\lessons\"Awesome Baduk" --out board_out
rem  Otro origen:  _subir_board.bat "RUTA\lessons"   (sin barra final)
rem  scp -r fusiona con /opt/tsumevault/player/lessons: no borra nada y
rem  sobreescribe solo esos ficheros. Se puede repetir.
rem ------------------------------------------------------------------

set HOST=root@46.225.97.185
set SSH_OPTS=-o ServerAliveInterval=20 -o ServerAliveCountMax=12
set SRC=%~dp0board_out\lessons
if not "%~1"=="" set SRC=%~1

if not exist "%SRC%" (
  echo ERROR: no existe la carpeta de origen: %SRC%
  pause
  exit /b 1
)

set N_SGF=0
set N_JSON=0
set N_ALL=0
for /f %%i in ('dir /s /b /a-d "%SRC%\*.sgf" 2^>nul ^| find /c /v ""') do set N_SGF=%%i
for /f %%i in ('dir /s /b /a-d "%SRC%\*.json" 2^>nul ^| find /c /v ""') do set N_JSON=%%i
for /f %%i in ('dir /s /b /a-d "%SRC%" 2^>nul ^| find /c /v ""') do set N_ALL=%%i
set /a N_OK=N_SGF+N_JSON
echo Origen: %SRC%
echo Ficheros: %N_ALL%   ^(.sgf: %N_SGF%   .json: %N_JSON%^)

if "%N_ALL%"=="0" (
  echo ERROR: no hay ficheros en el origen.
  pause
  exit /b 1
)
if not "%N_OK%"=="%N_ALL%" (
  echo.
  echo ERROR: el origen tiene ficheros que NO son .sgf ni .json ^(audio, dibujos...^).
  echo Este script es solo para --board-only; usa la carpeta board_out\lessons. Abortando.
  pause
  exit /b 1
)
if not "%N_SGF%"=="%N_JSON%" (
  echo.
  echo ERROR: no hay el mismo numero de .sgf que de .json; cada leccion lleva los dos. Abortando.
  pause
  exit /b 1
)

echo.
echo Subiendo %N_JSON% lecciones ^(%N_ALL% ficheros^)...
scp -r %SSH_OPTS% "%SRC%" %HOST%:/opt/tsumevault/player/
if errorlevel 1 (
  echo.
  echo ERROR en la subida ^(conexion cortada?^). Vuelve a lanzar este script: es repetible.
  pause
  exit /b 1
)

echo.
echo Ajustando permisos para que Caddy pueda leer las carpetas ^(scp desde Windows las deja en 700^)...
ssh %SSH_OPTS% %HOST% "chmod -R a+rX /opt/tsumevault/player/lessons"
if errorlevel 1 (
  echo.
  echo AVISO: no se pudieron ajustar los permisos. Lanza a mano en el servidor:
  echo   chmod -R a+rX /opt/tsumevault/player/lessons
)

echo.
echo Listo.
pause
