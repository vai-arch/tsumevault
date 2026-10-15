@echo off
setlocal
REM ==== Sube las lecciones corregidas de la carpeta indicada (p. ej. fix_v24) ====
REM Ejecutar desde _sources_scripts\awesome_baduk, despues de empaquetar_fix.py
REM AJUSTA SRV si en tu _subir_lecciones.bat es distinto:
set "SRV=root@tsumevault.duckdns.org"
set "FIX=%~1"
if "%FIX%"=="" ( echo Uso: _subir_fix.bat fix_v24 & goto :fin )
set "REMOTE=/opt/tsumevault/player/lessons"
set "TAR=%FIX%\%FIX%.tar"
set "LISTA=%FIX%\%FIX%_lista.txt"

if not exist "%TAR%" ( echo ERROR: no existe %TAR% & goto :fin )
if not exist "%LISTA%" ( echo ERROR: no existe %LISTA% & goto :fin )

echo === 1. Comprobando en el servidor que existen los ficheros a sustituir (no se toca nada) ===
scp "%LISTA%" %SRV%:/root/%FIX%_lista.txt
if errorlevel 1 goto :error
ssh %SRV% "cd '%REMOTE%' && echo Ficheros en la lista: $(wc -l < /root/%FIX%_lista.txt) && echo Existen en el servidor: $(xargs -d '\n' -a /root/%FIX%_lista.txt ls 2>/dev/null | wc -l)"
if errorlevel 1 goto :error
echo Deben salir los dos numeros iguales. Si no, CANCELA con Ctrl+C.
pause

echo.
echo === 2. Copia de seguridad en el servidor de los ficheros que se van a sustituir ===
ssh %SRV% "cd '%REMOTE%' && tar -cf /root/backup_antes_%FIX%_$(date +%%Y%%m%%d-%%H%%M%%S).tar -T /root/%FIX%_lista.txt && ls -la /root/backup_antes_%FIX%_*.tar"
if errorlevel 1 goto :error

echo.
echo === 3. Subiendo y descomprimiendo (sobrescribe solo esos .sgf y .json) ===
scp "%TAR%" %SRV%:/root/%FIX%.tar
if errorlevel 1 goto :error
ssh %SRV% "cd '%REMOTE%' && tar -xf /root/%FIX%.tar --no-same-owner && xargs -d '\n' -a /root/%FIX%_lista.txt chown --reference='Awesome Baduk' && xargs -d '\n' -a /root/%FIX%_lista.txt chmod a+r && rm -f /root/%FIX%.tar && echo Actualizados: $(xargs -d '\n' -a /root/%FIX%_lista.txt -I{} find {} -mmin -5 | wc -l)"
if errorlevel 1 goto :error

echo.
echo === Hecho ===
echo "Actualizados" debe ser igual a "Ficheros en la lista". Recarga el player con Ctrl+F5.
echo La copia de seguridad queda en /root/backup_antes_%FIX%_*.tar del servidor.
goto :fin

:error
echo.
echo *** ERROR: el paso anterior ha fallado. Nada posterior se ha ejecutado.

:fin
pause
endlocal
