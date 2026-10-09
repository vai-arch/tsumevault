@echo off
setlocal
pushd "%~dp0"

REM Importa la fuente awesome_baduk en TsumeVault y despues sube los SGF a GitHub Pages.
REM --source y --sgf-prefix son imprescindibles: sin ellos cargaria en my_collections.

if not exist "awesome_baduk" (
  echo Falta la carpeta awesome_baduk con los SGF
  goto :error
)

powershell -NoProfile -Command "if (Get-ChildItem 'awesome_baduk' | Where-Object { $_.Name -notlike 'Level *' }) { exit 1 }"
if errorlevel 1 (
  echo La carpeta awesome_baduk contiene algo que no es Level NN. No se importa ni se sube nada.
  goto :error
)

python import_my_collections.py awesome_baduk --source awesome_baduk --sgf-prefix awesome_baduk --server https://tsumevault.duckdns.org
if errorlevel 1 (
  echo.
  echo El importador ha fallado o ha rechazado la carga. No se sube nada a GitHub.
  goto :error
)

echo.
echo Importacion correcta. Revisa el resultado de arriba antes de subir.
pause

call subir_awesome_baduk.bat
popd
goto :eof

:error
echo.
echo *** ERROR: el proceso se ha detenido. ***
pause
popd
goto :eof