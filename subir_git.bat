@echo off

echo Parando servidores...
call _paraServidor.bat

echo Cerrando WAL de SQLite...
sqlite3 tsumeVault.db "PRAGMA wal_checkpoint(TRUNCATE)"

echo Bajando base de datos de Hetzner...
scp root@46.225.97.185:/opt/tsumevault/tsumeVault.db "%~dp0tsumeVault.db"

echo Añadiendo base de datos...
git add -f tsumeVault.db

echo Commit y push...
git add -A && git commit -m "update" && git push

echo Todo hecho.
pause