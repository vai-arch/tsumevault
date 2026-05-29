echo Subiendo base de datos a Hetzner...
ssh root@46.225.97.185 "systemctl stop tsumevault && sqlite3 /opt/tsumevault/tsumeVault.db 'PRAGMA wal_checkpoint(TRUNCATE);'"
scp "%~dp0tsumeVault.db" root@46.225.97.185:/opt/tsumevault/tsumeVault.db
ssh root@46.225.97.185 "systemctl start tsumevault"
echo Hecho.
pause