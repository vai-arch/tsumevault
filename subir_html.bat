@echo off

echo Actualizando versión SW...
python bump_version.py

echo subiendo HTML y sw.js
git add -f tsumeVault.html
git add -f sw.js
git add -f sync_push_log.json

echo Commit y push...
git commit -m "html update" && git push

echo Todo hecho.
pause