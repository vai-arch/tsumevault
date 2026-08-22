@echo off

echo Actualizando versión SW...
python bump_version.py

echo subiendo HTML y sw.js
git add -f tsumevault.html
git add -f sw.js

echo Commit y push...
git commit -m "html update" && git push

echo Todo hecho.
pause