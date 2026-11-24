@echo off

call "%~dp0_sqlite_path.bat"
if not defined SQLITE (
    echo ERROR: no encuentro sqlite3 ^(ni en conda ni en el PATH^). Anade su ruta en _sqlite_path.bat.
    pause
    exit /b 1
)

echo Parando servidores...
REM call _paraServidor.bat

echo Cerrando WAL de SQLite...
"%SQLITE%" tsumeVault.db "PRAGMA wal_checkpoint(TRUNCATE)"

del tsumeVault.db

echo Bajando base de datos de Hetzner...

echo Creando snapshot consistente en Hetzner (sin parar el servicio)...
ssh root@46.225.97.185 "cd /opt/tsumevault && rm -f tsumevault_snapshot.db && sqlite3 tsumeVault.db '.backup tsumevault_snapshot.db' && sqlite3 tsumevault_snapshot.db 'VACUUM;' && sqlite3 tsumevault_snapshot.db 'PRAGMA integrity_check;'"
echo ^^^ Debe haber impreso "ok". Si no, NO continues.
pause
echo Descargando...
scp root@46.225.97.185:/opt/tsumevault/tsumevault_snapshot.db "%~dp0tsumeVault.db"
echo Verificando la copia local...
"%SQLITE%" "%~dp0tsumeVault.db" "PRAGMA integrity_check;"
echo ^^^ Debe imprimir "ok". Hecho.


echo Actualizando versión SW...
python bump_version.py

echo Añadiendo base de datos...
git add -f tsumeVault.db

echo Commit y push...
git add -A && git commit -m "update" && git push

echo Todo hecho.
pause

