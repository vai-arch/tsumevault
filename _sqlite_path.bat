@echo off
rem Deja en SQLITE la ruta de sqlite3.exe, o vacia si no lo encuentra. Uso, desde otro .bat:
rem     call "%~dp0_sqlite_path.bat"
rem     if not defined SQLITE (echo ERROR: no encuentro sqlite3 & pause & exit /b 1)
rem Busca en el conda del usuario actual (miniconda3 o anaconda3), en el del otro PC
rem (C:\Users\Usuario) y, si no, en el PATH (p. ej. desde un Anaconda Prompt activado).
set "SQLITE="
for %%P in ("%USERPROFILE%\miniconda3\Library\bin\sqlite3.exe" "%USERPROFILE%\anaconda3\Library\bin\sqlite3.exe" "C:\Users\Usuario\miniconda3\Library\bin\sqlite3.exe") do (
    if not defined SQLITE if exist "%%~P" set "SQLITE=%%~P"
)
if defined SQLITE goto :eof
where sqlite3 >nul 2>&1
if not errorlevel 1 set "SQLITE=sqlite3"
