@echo off
setlocal EnableExtensions
title Subir lecciones Awesome Baduk a Hetzner

rem USO:
rem   _subir_lecciones_a_Hetzner.bat                       -> sube TODA la carpeta "Awesome Baduk" (unos 3.5 GB)
rem   _subir_lecciones_a_Hetzner.bat "Nombre de la carpeta" -> sube SOLO esa carpeta de curso
rem      (el nombre exacto lo imprime awesome_to_player.py al terminar: "Carpetas de curso generadas")
rem
rem ===================== CONFIGURACION (edita si hace falta) =====================
set "SRV=root@46.225.97.185"
set "REMOTE=/opt/tsumevault/player"
set "LESSONS=%~dp0lessons"
set "MANIFEST=%~dp0all_lessons.json"
set "TAR=%TEMP%\awesome_baduk_lessons.tar"
set "REFDIR=Middle game"
rem LESSONS = la carpeta "lessons" local (junto a este .bat); se sube SOLO "Awesome Baduk" o una carpeta de curso
rem REFDIR = una carpeta que YA exista en lessons: se copia su propietario/grupo a la nueva
rem ================================================================================

set "SUBPATH=Awesome Baduk"
set "TARPATH=Awesome Baduk"
set "RSUB=Awesome Baduk"
if not "%~1"=="" set "SUBPATH=Awesome Baduk\%~1"
if not "%~1"=="" set "TARPATH=Awesome Baduk/%~1"
if not "%~1"=="" set "RSUB=Awesome Baduk/%~1"

echo === 0. Comprobando rutas locales ===
echo Se subira: "%SUBPATH%"
if not exist "%LESSONS%\%SUBPATH%\" (
  echo ERROR: no existe "%LESSONS%\%SUBPATH%"
  echo Revisa el nombre de la carpeta del curso o la variable LESSONS de este .bat
  goto :fin
)
if not exist "%MANIFEST%" (
  echo ERROR: no existe "%MANIFEST%"
  goto :fin
)
for /f %%i in ('dir /s /b /a-d "%LESSONS%\%SUBPATH%" ^| find /c /v ""') do set "LOCAL_COUNT=%%i"
echo Ficheros locales a subir: %LOCAL_COUNT%

echo.
echo === 1. Mirando el servidor (todavia NO se toca nada) ===
ssh %SRV% "ls '%REMOTE%/lessons'; echo; df -h /opt/tsumevault | tail -1; ls -la '%REMOTE%/all_lessons.json'"
if errorlevel 1 goto :error
echo.
echo Mira arriba: deben verse los tipos de leccion, el espacio libre y all_lessons.json.
echo Si algo no cuadra, CANCELA con Ctrl+C.
pause

echo.
echo === 2. Empaquetando (si es toda la carpeta, varios minutos) ===
if exist "%TAR%" del "%TAR%"
tar -cf "%TAR%" -C "%LESSONS%" "%TARPATH%"
if errorlevel 1 goto :error

echo.
echo === 3. Subiendo el paquete al servidor ===
scp "%TAR%" %SRV%:/root/awesome_baduk_lessons.tar
if errorlevel 1 goto :error

echo.
echo === 4. Descomprimiendo en el servidor (no borra nada de lo que ya hay) ===
ssh %SRV% "cd '%REMOTE%/lessons' && tar -xf /root/awesome_baduk_lessons.tar && rm -f /root/awesome_baduk_lessons.tar && chown -R --reference='%REFDIR%' 'Awesome Baduk' && chmod -R a+rX 'Awesome Baduk'"
if errorlevel 1 goto :error
del "%TAR%"

echo.
echo === 5. Verificando que no falta nada ===
ssh %SRV% "n=$(find '%REMOTE%/lessons/%RSUB%' -type f | wc -l); echo Ficheros en el PC       : %LOCAL_COUNT%; echo Ficheros en el servidor : $n; [ $n -eq %LOCAL_COUNT% ]"
if errorlevel 1 (
  echo ERROR: los numeros no coinciden. NO sigas con el all_lessons.json.
  goto :fin
)
ssh %SRV% "ls '%REMOTE%/lessons/%RSUB%' | head -5; du -sh '%REMOTE%/lessons/%RSUB%'"
echo.
echo Lecciones subidas y verificadas. Siguiente paso: reemplazar all_lessons.json
echo (se hace copia de seguridad en el servidor antes).
pause

echo.
echo === 6. all_lessons.json: copia de seguridad, validacion y reemplazo ===
ssh %SRV% "cp -p '%REMOTE%/all_lessons.json' '%REMOTE%/all_lessons.json.bak-'$(date +%%Y%%m%%d-%%H%%M%%S)"
if errorlevel 1 goto :error
scp "%MANIFEST%" %SRV%:%REMOTE%/all_lessons.json.nuevo
if errorlevel 1 goto :error
ssh %SRV% "cd '%REMOTE%' && python3 -m json.tool all_lessons.json.nuevo > /dev/null && echo Lecciones en el fichero nuevo: $(grep -c lessonId all_lessons.json.nuevo) && chown --reference=all_lessons.json all_lessons.json.nuevo && chmod --reference=all_lessons.json all_lessons.json.nuevo && mv all_lessons.json.nuevo all_lessons.json && echo REEMPLAZADO"
if errorlevel 1 goto :error

echo.
echo === Hecho ===
echo Recarga la web con Ctrl+F5 y abre una leccion de "Awesome Baduk".
goto :fin

:error
echo.
echo *** ERROR: el paso anterior ha fallado. Si el fallo fue antes del paso 6, el all_lessons.json
echo *** del servidor no se ha tocado.

:fin
pause
endlocal
