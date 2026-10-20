@echo off
cd /d "%~dp0"

echo ===== 1/3 Validando los maestros (no escribe nada) =====
python import_joseki.py joseki --validate-only
if errorlevel 1 (
  echo.
  echo Hay errores: no se sigue. Revisa el informe de arriba.
  pause
  exit /b 1
)

echo.
echo ===== 2/3 Compilando JSON y manifest.json =====
python import_joseki.py joseki --no-tree
if errorlevel 1 (
  echo.
  echo La compilacion ha fallado: no se sube nada.
  pause
  exit /b 1
)

echo.
echo ===== 3/3 Subiendo a GitHub =====
call subir_joseki.bat
