@echo off
setlocal
pushd "%~dp0"
set PYTHONIOENCODING=utf-8

REM ===== Config (ajusta SERVER si tu servidor de produccion tiene otra URL) =====
set SERVER=https://tsumevault.duckdns.org
set SOURCE=awesome_lessons
set ROOT=..\..\awesome_lessons
set IMPORTER=..\..\import_my_collections.py
REM El token NO se escribe aqui: se lee de la variable de entorno TSUMEVAULT_TOKEN.
REM En PowerShell:  $env:TSUMEVAULT_TOKEN = "tu_token"   y luego lanza este .bat desde esa misma ventana.
REM ==============================================================================

if not exist "%ROOT%" (
  echo No existe la carpeta %ROOT%
  goto :error
)
if not exist "%IMPORTER%" (
  echo No existe el importador %IMPORTER%
  goto :error
)

echo === 1/3 Validando %ROOT% (no contacta con ningun servidor) ===
python "%IMPORTER%" "%ROOT%" --source %SOURCE% --sgf-prefix %SOURCE% --validate-only
if errorlevel 1 goto :error

echo.
echo === 2/3 ANTES DE SEGUIR, comprueba que: ===
echo   - Los SGF de %SOURCE% ya estan subidos y servidos por la web (git push hecho).
echo   - Has hecho una copia de seguridad de la base de datos de produccion (sqlite .backup).
echo   - Se va a importar en: %SERVER%
echo.
set /p CONF=Escribe SI para importar en PRODUCCION: 
if /i not "%CONF%"=="SI" goto :cancel

echo.
echo === 3/3 Importando en %SERVER% ===
python "%IMPORTER%" "%ROOT%" --source %SOURCE% --sgf-prefix %SOURCE% --server %SERVER%
if errorlevel 1 goto :error

echo.
echo Importacion terminada. Esperado la primera vez: 6 colecciones, 443 capitulos nuevos, 5571 problemas.
pause
popd
goto :eof

:cancel
echo Cancelado, no se ha importado nada.
pause
popd
goto :eof

:error
echo.
echo *** ERROR: el proceso se ha detenido. Revisa el mensaje de arriba. ***
pause
popd
goto :eof
