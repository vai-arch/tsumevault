@echo off
echo === 1. Comprobando que el servidor NO tiene datos mas nuevos que la copia local ===
ssh root@46.225.97.185 "sqlite3 /opt/tsumevault/tsumeVault.db \"SELECT MAX(created_at) FROM attempts;\""
C:\Users\Usuario\miniconda3\Library\bin\sqlite3.exe "%~dp0tsumeVault.db" "SELECT MAX(created_at) FROM attempts;"
echo ^^^ Si NO coinciden, CANCELA con Ctrl+C: hay attempts en el servidor que se perderian.
pause

echo === 2. Parando servicio, backup del fichero actual, limpieza de WAL viejo ===
ssh root@46.225.97.185 "systemctl stop tsumevault && cd /opt/tsumevault && sqlite3 tsumeVault.db '.backup tsumeVault_pre_subida.db' && rm -f tsumeVault.db-wal tsumeVault.db-shm"

echo === 3. Subiendo BD reparada ===
scp "%~dp0tsumeVault.db" root@46.225.97.185:/opt/tsumevault/tsumeVault.db

echo === 4. Verificando la subida y arrancando ===
ssh root@46.225.97.185 "cd /opt/tsumevault && sqlite3 tsumeVault.db 'PRAGMA integrity_check;' && systemctl start tsumevault"
echo ^^^ Debe haber impreso "ok" antes de arrancar. Hecho.
pause