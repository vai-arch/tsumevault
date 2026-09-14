@echo off

echo subiendo my_collections
git add -f my_collections

echo Commit y push...
git commit -m "my collections update" && git push

echo Todo hecho.
pause