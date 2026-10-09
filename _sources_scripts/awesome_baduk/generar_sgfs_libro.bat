@echo off
setlocal
pushd "%~dp0"

REM El libro debe estar en esta carpeta, con este nombre
set EPUB_FILE=Mastering Basic Corner Shapes_interactive.epub
set PYTHONIOENCODING=utf-8

if not exist "convertir_libro.py" (
  echo Falta el script convertir_libro.py
  goto :error
)
if not exist "%EPUB_FILE%" (
  echo Falta el libro: %EPUB_FILE%
  goto :error
)

echo === Limpiando la salida anterior del libro ===
powershell -NoProfile -Command "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue salida_libro, informe_libro.txt"

echo.
echo === Convirtiendo el libro a SGF ===
python convertir_libro.py "%EPUB_FILE%"
if errorlevel 1 goto :error

echo.
powershell -NoProfile -Command "Write-Host ('Terminado. Ficheros SGF generados: ' + (Get-ChildItem 'salida_libro' -Recurse -Filter '*.sgf').Count)"
echo Revisa informe_libro.txt: lista los diagramas que no se pudieron convertir.
echo Despues copia salida_libro a my_collections para importarlo.
pause
popd
goto :eof

:error
echo.
echo *** ERROR: el proceso se ha detenido. Revisa el mensaje de arriba. ***
pause
popd
goto :eof