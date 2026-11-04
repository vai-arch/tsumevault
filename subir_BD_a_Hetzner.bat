@echo off
setlocal
rem ============================================================
rem  Sube la BD de trabajo (tsumeVault.db) a Hetzner.
rem  Antes comprueba que el servidor NO ha recibido datos nuevos
rem  desde la descarga (compara contra tsumeVault.downloaded.db).
rem ============================================================
set "HOST=root@46.225.97.185"
set "RDIR=/opt/tsumevault"
set "SERVICE=tsumevault"
set "SQLITE=C:\Users\Usuario\miniconda3\Library\bin\sqlite3.exe"
if exist "%SQLITE%" goto :sqlite_ok
where sqlite3 >nul 2>&1
if errorlevel 1 goto :no_sqlite
set "SQLITE=sqlite3"
:sqlite_ok
set "LOCAL=%~dp0tsumeVault.db"
set "ORIG=%~dp0tsumeVault.downloaded.db"
set "T1=%TEMP%\tsv_subir_1.txt"
set "T2=%TEMP%\tsv_subir_2.txt"

rem Huella: recuentos y fechas maximas de las tablas que cambian por sincronizacion.
set "FP=SELECT (SELECT COUNT(*) FROM attempts), COALESCE((SELECT MAX(created_at) FROM attempts),0), (SELECT COUNT(*) FROM runs), COALESCE((SELECT MAX(id) FROM runs),0), (SELECT COUNT(*) FROM sm2_state), COALESCE((SELECT MAX(updated_at) FROM sm2_state),0), (SELECT COUNT(*) FROM problem_tags), COALESCE((SELECT MAX(updated_at) FROM problem_tags),0), (SELECT COUNT(*) FROM tags), (SELECT COUNT(*) FROM focus), COALESCE((SELECT MAX(updated_at) FROM focus),0), (SELECT COUNT(*) FROM focus_chapters), COALESCE((SELECT MAX(updated_at) FROM focus_chapters),0), (SELECT COUNT(*) FROM focus_sessions), COALESCE((SELECT MAX(updated_at) FROM focus_sessions),0), (SELECT COUNT(*) FROM joseki_sm2), (SELECT COUNT(*) FROM joseki_attempts), (SELECT COUNT(*) FROM virtual_collections);"

for /f %%i in ('powershell -nologo -noprofile -command "Get-Date -Format yyyyMMdd-HHmmss"') do set "TS=%%i"

echo === 0. Comprobaciones locales ===
if not exist "%LOCAL%" goto :nolocal
if not exist "%ORIG%" goto :noorig
set "R="
"%SQLITE%" "%LOCAL%" "PRAGMA integrity_check;" > "%T1%"
set /p R=<"%T1%"
if /i not "%R%"=="ok" goto :badlocal
echo BD local: integrity_check ok
fc /b "%LOCAL%" "%ORIG%" >nul 2>&1
if not errorlevel 1 echo AVISO: la BD local es IDENTICA a la descargada ^(aun no has aplicado cambios^).

echo.
echo Se va a PARAR el servicio, subir la BD local y volver a arrancarlo.
echo El servidor guarda antes una copia: tsumeVault_pre_subida_%TS%.db
choice /c SN /d N /t 600 /m "Continuar"
if errorlevel 2 goto :cancel

echo.
echo === 1. Parando el servicio ===
ssh %HOST% "systemctl stop %SERVICE%"
if errorlevel 1 goto :fail_nostop

echo.
echo === 2. Comprobando que el servidor no tiene datos mas nuevos que la descarga ===
set "F_SRV="
set "F_ORIG="
ssh %HOST% "sqlite3 %RDIR%/tsumeVault.db '%FP%'" > "%T1%"
if errorlevel 1 goto :fail_restart
"%SQLITE%" "%ORIG%" "%FP%" > "%T2%"
if errorlevel 1 goto :fail_restart
set /p F_SRV=<"%T1%"
set /p F_ORIG=<"%T2%"
if "%F_SRV%"=="" goto :fail_restart
if not "%F_SRV%"=="%F_ORIG%" goto :mismatch
echo Sin cambios en el servidor desde la descarga: ok

echo.
echo === 3. Copia de seguridad en el servidor ===
ssh %HOST% "cd %RDIR% && sqlite3 tsumeVault.db '.backup tsumeVault_pre_subida_%TS%.db'"
if errorlevel 1 goto :fail_restart

echo.
echo === 4. Subiendo a un fichero temporal ===
scp "%LOCAL%" %HOST%:%RDIR%/tsumeVault.db.new
if errorlevel 1 goto :fail_restart

echo.
echo === 5. Verificando lo subido ===
set "R="
ssh %HOST% "sqlite3 %RDIR%/tsumeVault.db.new 'PRAGMA integrity_check;'" > "%T1%"
if errorlevel 1 goto :fail_restart
set /p R=<"%T1%"
if /i not "%R%"=="ok" goto :fail_restart
set "F_SRV="
set "F_LOC="
ssh %HOST% "sqlite3 %RDIR%/tsumeVault.db.new '%FP%'" > "%T1%"
if errorlevel 1 goto :fail_restart
"%SQLITE%" "%LOCAL%" "%FP%" > "%T2%"
set /p F_SRV=<"%T1%"
set /p F_LOC=<"%T2%"
if "%F_SRV%"=="" goto :fail_restart
if not "%F_SRV%"=="%F_LOC%" goto :fail_restart
echo Fichero subido: integrity ok y contenido igual al local

echo.
echo === 6. Sustituyendo la BD ^(conserva propietario y permisos; limpia WAL/SHM viejos^) ===
ssh %HOST% "cd %RDIR% && chown --reference=tsumeVault.db tsumeVault.db.new && chmod --reference=tsumeVault.db tsumeVault.db.new && rm -f tsumeVault.db-wal tsumeVault.db-shm && mv -f tsumeVault.db.new tsumeVault.db"
if errorlevel 1 goto :fail_swap

echo.
echo === 7. Arrancando el servicio ===
ssh %HOST% "systemctl start %SERVICE% && sleep 2 && systemctl is-active %SERVICE%"
if errorlevel 1 goto :fail_start

echo.
echo Hecho. Copia previa en el servidor: %RDIR%/tsumeVault_pre_subida_%TS%.db
echo Siguiente: subir los .sgf nuevos e importar ^(import_my_collections.py^).
pause
exit /b 0

:nolocal
echo ERROR: no existe %LOCAL%
pause
exit /b 1

:noorig
echo ERROR: no existe %ORIG%. Ejecuta primero bajar_BD_de_Hetzner.bat.
pause
exit /b 1

:badlocal
echo ERROR: la BD local no pasa integrity_check ^(devolvio: %R%^). No se sube nada.
pause
exit /b 1

:cancel
echo.
echo Cancelado. No se ha tocado el servidor.
pause
exit /b 0

:fail_nostop
echo.
echo ERROR: no se pudo parar el servicio. No se ha tocado nada.
pause
exit /b 1

:mismatch
echo.
echo ERROR: el servidor tiene datos DISTINTOS a los de la descarga ^(alguien sincronizo^).
echo   servidor: %F_SRV%
echo   descarga: %F_ORIG%
echo Subir ahora perderia esos datos. Se reinicia el servicio y se aborta.
echo Vuelve a bajar la BD y repite el borrado.
goto :restart_and_exit

:fail_restart
echo.
echo ERROR: un paso ha fallado ANTES de sustituir la BD. La BD del servidor esta intacta.
echo Se reinicia el servicio.
goto :restart_and_exit

:restart_and_exit
ssh %HOST% "systemctl start %SERVICE%"
pause
exit /b 1

:fail_swap
echo.
echo ERROR al sustituir la BD. El servicio sigue PARADO.
echo Copia previa: %RDIR%/tsumeVault_pre_subida_%TS%.db
echo Revisa el estado del servidor antes de arrancar.
pause
exit /b 1

:fail_start
echo.
echo ERROR: el servicio no arranca. La BD ya esta sustituida.
echo Mira: ssh %HOST% "journalctl -u %SERVICE% -n 40 --no-pager"
echo Copia previa: %RDIR%/tsumeVault_pre_subida_%TS%.db
pause
exit /b 1

:no_sqlite
echo.
echo ERROR: no encuentro sqlite3 en esta maquina ^(ni en la ruta de SQLITE ni en el PATH^).
echo Ejecuta "where sqlite3" en cmd, o corrige la linea set "SQLITE=..." al principio.
pause
exit /b 1
