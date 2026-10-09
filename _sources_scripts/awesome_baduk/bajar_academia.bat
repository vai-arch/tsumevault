@echo off
setlocal
pushd "%~dp0"

REM Sin argumentos baja todos los niveles. Ejemplos:
REM   bajar_academia.bat          todos
REM   bajar_academia.bat 1        solo el Level 01
REM   bajar_academia.bat 1,2,3    los niveles 01, 02 y 03
set NIVELES=%*
if "%NIVELES%"=="" set NIVELES=todos
set PYTHONIOENCODING=utf-8

for %%F in (niveles_academia.py list_inventory.py analyze_all.py convert_problems.py) do (
  if not exist "%%F" (
    echo Falta el script %%F
    goto :error
  )
)
if not exist "awesomebaduk_rt" (
  echo Falta el fichero del refresh token: awesomebaduk_rt
  goto :error
)

echo === Bajando y convirtiendo los problemas de la academia, niveles: %NIVELES% ===
echo Es reanudable: lo que ya esta en problems_raw no se vuelve a bajar.
echo Si tarda mucho, puedes pararlo con Ctrl+C y lanzarlo de nuevo.
echo.
python niveles_academia.py %NIVELES%
if errorlevel 1 goto :error

echo.
powershell -NoProfile -Command "Write-Host ('Problemas en la cache: ' + (Get-ChildItem 'problems_raw' -Filter '*.json').Count)"
powershell -NoProfile -Command "Write-Host ('SGF generados en salida_academia: ' + (Get-ChildItem 'salida_academia' -Recurse -Filter '*.sgf').Count)"
echo Revisa informe_niveles.txt: lista lo que no se pudo bajar o convertir.
echo Despues copia salida_academia a my_collections para importarlo.
pause
popd
goto :eof

:error
echo.
echo *** ERROR: el proceso se ha detenido. Revisa el mensaje de arriba. ***
pause
popd
goto :eof