echo Bajando base de datos de Hetzner...
ssh root@46.225.97.185 "systemctl stop tsumevault && sqlite3 /opt/tsumevault/tsumeVault.db 'PRAGMA wal_checkpoint(TRUNCATE);'"
scp root@46.225.97.185:/opt/tsumevault/tsumeVault.db "%~dp0tsumeVault.db"
ssh root@46.225.97.185 "systemctl start tsumevault"
echo Hecho.