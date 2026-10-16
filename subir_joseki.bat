@echo off

echo subiendo joseki
git add -f joseki

echo Commit y push...
git commit -m "joseki update" && git push

echo Todo hecho.
pause