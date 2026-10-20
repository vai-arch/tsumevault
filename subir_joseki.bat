@echo off
cd /d "%~dp0"

echo subiendo joseki
git add -f "joseki/*.sgf" "joseki/*.json"

git diff --cached --quiet -- joseki
if not errorlevel 1 (
  echo No hay cambios en joseki: nada que subir.
  pause
  exit /b 0
)

echo Commit y push...
git commit -m "joseki update" && git push
if errorlevel 1 (
  echo.
  echo La subida ha fallado: revisa los mensajes de git arriba.
  pause
  exit /b 1
)

echo Todo hecho.
pause
