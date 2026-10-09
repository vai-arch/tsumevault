@echo off
setlocal
pushd "%~dp0"

powershell -NoProfile -Command "if (Get-ChildItem 'awesome_baduk' | Where-Object { $_.Name -notlike 'Level *' }) { exit 1 }"
if errorlevel 1 (
  echo La carpeta awesome_baduk contiene algo que no es Level NN. No se sube nada.
  pause
  popd
  goto :eof
)

echo subiendo awesome_baduk
git add -f awesome_baduk

echo Commit y push...
git commit -m "awesome_baduk update" && git push

echo Todo hecho.
pause
popd