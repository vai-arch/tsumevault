@echo off
setlocal
pushd "%~dp0"

REM Debe coincidir con RT_PATH de los scripts .py
set RT_FILE=awesomebaduk_rt

for %%F in (read_challenge.py download_days.py download_all_problems.py convert_problems.py analyze_all.py) do (
  if not exist "%%F" (
    echo Falta el script %%F
    goto :error
  )
)
if not exist "%RT_FILE%" (
  echo Falta el fichero del refresh token: %RT_FILE%
  goto :error
)

echo === Limpiando datos generados ===
powershell -NoProfile -Command "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue challenge.json, days.json, problems_raw, salida_sgf"

echo.
echo === Paso 1 de 4: descargando el desafio ===
python read_challenge.py
if errorlevel 1 goto :error

echo.
echo === Paso 2 de 4: descargando los dias ===
python download_days.py
if errorlevel 1 goto :error

echo.
echo === Paso 3 de 4: descargando los problemas ===
python download_all_problems.py
if errorlevel 1 goto :error

echo.
echo === Paso 4 de 4: convirtiendo a SGF ===
python convert_problems.py
if errorlevel 1 goto :error

echo.
powershell -NoProfile -Command "Write-Host ('Terminado. Ficheros SGF generados: ' + (Get-ChildItem 'salida_sgf' -Recurse -Filter '*.sgf').Count)"
pause
popd
goto :eof

:error
echo.
echo *** ERROR: el proceso se ha detenido. Revisa el mensaje de arriba. ***
pause
popd
goto :eof