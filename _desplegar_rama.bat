@echo off
setlocal
rem Despliega una rama preparada por Claude: la fusiona en main, sube el servidor
rem al VPS (_subir_servidor.bat) y deja main igual en GitHub. Si la rama cambia el
rem cliente, sube tambien la version del service worker (tools\bump_version.py) para
rem que los moviles no se queden con la copia en cache.
rem Uso:  .\_desplegar_rama.bat nombre-de-la-rama      (por ejemplo: pachi)
if "%~1"=="" (
    echo Uso: %~nx0 nombre-de-la-rama
    pause
    exit /b 1
)
set "RAMA=%~1"
cd /d "%~dp0"

git diff --quiet && git diff --cached --quiet || (
    echo ERROR: hay cambios sin commit. Guardalos o descartalos antes de desplegar.
    pause
    exit /b 1
)

echo Bajando de GitHub...
git fetch || goto :error
git switch main || goto :error
git merge --ff-only origin/main || goto :error

echo.
echo Cambios de la rama %RAMA%:
git --no-pager diff --stat main origin/%RAMA% || goto :error
set "CLIENTE="
for /f %%F in ('git --no-pager diff --name-only main origin/%RAMA% -- tsumevault.html lessons.html player.html sw.js manifest.json js wgo') do set "CLIENTE=1"

echo.
echo Fusionando %RAMA% en main...
git merge --ff-only origin/%RAMA% || (
    echo ERROR: no se puede fusionar sin conflictos. Avisa a Claude.
    pause
    exit /b 1
)

if defined CLIENTE (
    echo.
    echo La rama cambia el cliente: subiendo la version del service worker...
    python "%~dp0tools\bump_version.py" || goto :error
    git add sw.js tsumevault.html || goto :error
    git commit -m "bump service worker (%RAMA%)" || goto :error
)

call "%~dp0_subir_servidor.bat"

echo Subiendo main a GitHub...
git push || goto :error
echo.
echo Hecho: %RAMA% desplegada.
pause
exit /b 0

:error
echo.
echo ERROR: algo ha fallado. Revisa el mensaje de arriba antes de seguir.
pause
exit /b 1
