@echo off
setlocal
REM ==== Sube las 35 lecciones corregidas (v23, color de piedras) al servidor ====
REM Ejecutar desde _sources_scripts\awesome_baduk, despues de empaquetar_fix.py
REM AJUSTA SRV si en tu _subir_lecciones.bat es distinto:
set "SRV=root@tsumevault.duckdns.org"
set "REMOTE=/opt/tsumevault/player/lessons"
set "TAR=fix_v23\fix_v23.tar"
set "LISTA=fix_v23\fix_v23_lista.txt"

if not exist "%TAR%" ( echo ERROR: no existe %TAR% & goto :fin )
if not exist "%LISTA%" ( echo ERROR: no existe %LISTA% & goto :fin )

echo === 1. Comprobando en el servidor que existen los ficheros a sustituir (no se toca nada) ===
scp "%LISTA%" %SRV%:/root/fix_v23_lista.txt
if errorlevel 1 goto :error
ssh %SRV% "cd '%REMOTE%' && echo Ficheros en la lista: $(wc -l < /root/fix_v23_lista.txt) && echo Existen en el servidor: $(xargs -d '\n' -a /root/fix_v23_lista.txt ls 2>/dev/null | wc -l)"
if errorlevel 1 goto :error
echo Deben salir los dos numeros iguales (70). Si no, CANCELA con Ctrl+C.
pause

echo.
echo === 2. Copia de seguridad en el servidor de los ficheros que se van a sustituir ===
ssh %SRV% "cd '%REMOTE%' && tar -cf /root/backup_antes_fix_v23_$(date +%%Y%%m%%d-%%H%%M%%S).tar -T /root/fix_v23_lista.txt && ls -la /root/backup_antes_fix_v23_*.tar"
if errorlevel 1 goto :error

echo.
echo === 3. Subiendo y descomprimiendo (sobrescribe solo esos .sgf y .json) ===
scp "%TAR%" %SRV%:/root/fix_v23.tar
if errorlevel 1 goto :error
ssh %SRV% "cd '%REMOTE%' && tar -xf /root/fix_v23.tar --no-same-owner && xargs -d '\n' -a /root/fix_v23_lista.txt chown --reference='Awesome Baduk' && xargs -d '\n' -a /root/fix_v23_lista.txt chmod a+r && rm -f /root/fix_v23.tar && echo Actualizados: $(xargs -d '\n' -a /root/fix_v23_lista.txt find -mmin -5 | wc -l)"
if errorlevel 1 goto :error

echo.
echo === Hecho ===
echo Debe decir "Actualizados: 70". Recarga el player con Ctrl+F5.
echo La copia de seguridad queda en /root/backup_antes_fix_v23_*.tar del servidor.
goto :fin

:error
echo.
echo *** ERROR: el paso anterior ha fallado. Nada posterior se ha ejecutado.

:fin
pause
endlocal
