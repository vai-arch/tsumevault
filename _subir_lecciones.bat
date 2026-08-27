@echo off
echo Creando carpeta player\ en el servidor si no existe...
ssh root@46.225.97.185 "mkdir -p /opt/tsumevault/player"

echo Subiendo manifest (all_lessons.json)...
scp "%~dp0player\all_lessons.json" root@46.225.97.185:/opt/tsumevault/player/

echo Subiendo lecciones (sgf/json/ogg)... esto puede tardar, son varios GB.
scp -r "%~dp0player\lessons" root@46.225.97.185:/opt/tsumevault/player/

echo.
echo Listo. NOTA: studied.json y recorded.json NO se suben (uso solo local).
pause
