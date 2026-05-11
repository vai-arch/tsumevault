@echo off

echo Parando servidores...
call _paraServidor.bat

echo Cerrando WAL de SQLite...
sqlite3 tsumeVault.db "PRAGMA wal_checkpoint(TRUNCATE)"

echo Añadiendo base de datos...
git add -f tsumeVault.db

echo Commit y push...
git add -A && git commit -m "update" && git push

echo Todo hecho.
pause