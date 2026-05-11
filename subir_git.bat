sqlite3 tsumeVault.db "PRAGMA wal_checkpoint(TRUNCATE)"
git add -f tsumeVault.db
git add -A && git commit -m "update" && git push

