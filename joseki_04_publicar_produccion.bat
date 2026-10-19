@echo off
cd /d "%~dp0"
set SERVER=https://tsumevault.duckdns.org

echo ===== 1/3 Generando los problemas (sin publicar) =====
python generate_joseki_problems.py joseki joseki_problems --no-publish
if errorlevel 1 (
  echo.
  echo Hay errores: no se sigue. Revisa el informe de arriba.
  pause
  exit /b 1
)

echo.
echo ===== 2/3 Subiendo a GitHub =====
call _subir_git.bat

echo.
echo ===== 3/3 Publicar en produccion (%SERVER%) =====
echo Si la subida a git ha ido bien, pulsa una tecla para publicar.
echo Si algo ha fallado, CIERRA esta ventana sin publicar.
pause
python generate_joseki_problems.py joseki joseki_problems --server %SERVER%
if errorlevel 1 (
  echo.
  echo La publicacion ha fallado: revisa la respuesta del servidor arriba.
)
pause