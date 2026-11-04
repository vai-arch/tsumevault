@echo off
setlocal
rem ============================================================
rem  Baja una copia consistente de la BD de Hetzner.
rem  Deja DOS ficheros junto a este .bat:
rem    tsumeVault.downloaded.db  copia ORIGINAL (no la toques; la usa subir_BD_a_Hetzner.bat)
rem    tsumeVault.db             copia de TRABAJO (sobre esta ejecutas delete_chapter.py)
rem ============================================================
set "HOST=root@46.225.97.185"
set "RDIR=/opt/tsumevault"
set "SQLITE=C:\Users\Usuario\miniconda3\Library\bin\sqlite3.exe"
if exist "%SQLITE%" goto :sqlite_ok
where sqlite3 >nul 2>&1
if errorlevel 1 goto :no_sqlite
set "SQLITE=sqlite3"
:sqlite_ok
set "LOCAL=%~dp0tsumeVault.db"
set "ORIG=%~dp0tsumeVault.downloaded.db"
set "TMPF=%TEMP%\tsv_bajar.txt"

rem --- Aviso si la BD local de trabajo tiene cambios que aun no se han subido ---
if not exist "%LOCAL%" goto :snapshot
if not exist "%ORIG%" goto :snapshot
fc /b "%LOCAL%" "%ORIG%" >nul 2>&1
if not errorlevel 1 goto :snapshot
echo.
echo AVISO: la BD local ^(tsumeVault.db^) es DISTINTA de la ultima descargada.
echo Si has editado la BD y aun no la has subido, descargar ahora la sobrescribe.
choice /c SN /d N /t 600 /m "Descargar igualmente y SOBRESCRIBIR la BD local"
if errorlevel 2 goto :cancel

:snapshot
echo.
echo === 1. Snapshot consistente en Hetzner ^(sin parar el servicio^) ===
ssh %HOST% "cd %RDIR% && rm -f tsumevault_snapshot.db && sqlite3 tsumeVault.db '.backup tsumevault_snapshot.db'"
if errorlevel 1 goto :fail
set "R="
ssh %HOST% "sqlite3 %RDIR%/tsumevault_snapshot.db 'PRAGMA integrity_check;'" > "%TMPF%"
if errorlevel 1 goto :fail
set /p R=<"%TMPF%"
if /i not "%R%"=="ok" goto :fail_integrity
echo Snapshot del servidor: ok

echo.
echo === 2. Descargando ===
del /q "%ORIG%" 2>nul
scp %HOST%:%RDIR%/tsumevault_snapshot.db "%ORIG%"
if errorlevel 1 goto :fail
set "R="
"%SQLITE%" "%ORIG%" "PRAGMA integrity_check;" > "%TMPF%"
set /p R=<"%TMPF%"
if /i not "%R%"=="ok" goto :fail_integrity
echo Copia descargada: ok

echo.
echo === 3. Creando la copia de trabajo ===
del /q "%LOCAL%-wal" 2>nul
del /q "%LOCAL%-shm" 2>nul
copy /y "%ORIG%" "%LOCAL%" >nul
if errorlevel 1 goto :fail

echo.
echo Hecho. Ahora: delete_chapter.py ^(dry-run, luego --apply^) sobre tsumeVault.db.
echo NO abras la app en ningun dispositivo hasta terminar todo el proceso.
pause
exit /b 0

:fail_integrity
echo.
echo ERROR: integrity_check no ha devuelto "ok" ^(devolvio: %R%^). NO continues.
pause
exit /b 1

:fail
echo.
echo ERROR: un paso ha fallado ^(ssh/scp/copia^). NO continues con la BD local.
pause
exit /b 1

:cancel
echo.
echo Cancelado. No se ha descargado nada.
pause
exit /b 0

:no_sqlite
echo.
echo ERROR: no encuentro sqlite3 en esta maquina ^(ni en la ruta de SQLITE ni en el PATH^).
echo Ejecuta "where sqlite3" en cmd, o corrige la linea set "SQLITE=..." al principio.
pause
exit /b 1
