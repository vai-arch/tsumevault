@echo off
call "%~dp0_sqlite_path.bat"
if not defined SQLITE (
    echo ERROR: no encuentro sqlite3 ^(ni en conda ni en el PATH^). Anade su ruta en _sqlite_path.bat.
    pause
    exit /b 1
)
"%SQLITE%" tsumeVault.db "PRAGMA wal_checkpoint(TRUNCATE)"
pause