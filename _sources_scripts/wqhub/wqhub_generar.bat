@echo off
setlocal
rem Genera los SGF de WeiqiHub en wqhub_sgf y despues los CSV de analisis.
rem Ejecutar desde un entorno con Python (p.ej. Anaconda PowerShell).
rem La carpeta wqhub_sgf y los CSV se borran y se regeneran en cada ejecucion.

cd /d "%~dp0"

if exist wqhub_sgf (
    echo Borrando wqhub_sgf anterior...
    rmdir /s /q wqhub_sgf
    if exist wqhub_sgf (
        echo ERROR: no se pudo borrar wqhub_sgf ^(algun fichero abierto?^)
        exit /b 1
    )
)

for %%F in (wqhub_capitulos.csv wqhub_problemas.csv wqhub_carpetas.csv) do (
    if exist %%F (
        echo Borrando %%F...
        del /q %%F
        if exist %%F (
            echo ERROR: no se pudo borrar %%F ^(abierto en Excel?^)
            exit /b 1
        )
    )
)

echo.
echo === Transformacion ===
python wqhub_to_sgf.py wqhub_tasks.db collections.json wqhub_sgf
if errorlevel 1 (
    echo.
    echo La transformacion ha terminado con errores; no se genera el analisis.
    exit /b 1
)

echo.
echo === Analisis ===
python wqhub_analisis.py wqhub_tasks.db collections.json
if errorlevel 1 exit /b 1

echo.
echo === Estadisticas de las carpetas generadas ===
python wqhub_carpetas.py wqhub_sgf
if errorlevel 1 exit /b 1

echo.
echo Listo: wqhub_sgf, wqhub_capitulos.csv, wqhub_problemas.csv y wqhub_carpetas.csv
endlocal
