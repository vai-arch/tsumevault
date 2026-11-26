@echo off
rem AR1.0: baja unas pocas muestras publicas de kifumaster.org a kifumaster\data\probe\
rem (una peticion cada 6-8 s). Ver kifumaster\README.md.
cd /d "%~dp0"
python "%~dp0kifumaster\kifu_probe.py"
pause
