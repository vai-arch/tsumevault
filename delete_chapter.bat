@echo off
rem ============================================================
rem  Borrar un capitulo de TsumeVault (dry-run + confirmacion)
rem  Para borrar otro capitulo, cambia SOLO las tres lineas "set".
rem ============================================================
set "SOURCE=my_collections"
set "COLLECTION=All About Life and Death - 01"
set "CHAPTER=01-Life and Death on the Second Line"
rem ============================================================

cd /d "%~dp0"

echo.
echo === DRY-RUN (no se modifica nada) ===
echo.
python delete_chapter.py --source "%SOURCE%" --collection "%COLLECTION%" --chapter "%CHAPTER%"
if errorlevel 1 (
    echo.
    echo El dry-run ha fallado. No se ha borrado nada.
    pause
    exit /b 1
)

echo.
echo ------------------------------------------------------------
echo Revisa los numeros de arriba. El servidor debe estar PARADO.
echo Si sigues, se hace una copia de seguridad y se borra de verdad.
echo ------------------------------------------------------------
choice /c SN /d N /t 600 /m "Borrar de verdad este capitulo (S=si, N=no)"
if errorlevel 2 (
    echo.
    echo Cancelado. No se ha borrado nada.
    pause
    exit /b 0
)

echo.
echo === BORRADO REAL ===
echo.
python delete_chapter.py --source "%SOURCE%" --collection "%COLLECTION%" --chapter "%CHAPTER%" --apply
echo.
pause