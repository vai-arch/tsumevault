@echo off
rem AR1: descarga los datos publicos de kifumaster.org a kifumaster\data\raw\ (una peticion cada 6-8 s,
rem unas 2 horas el primer ciclo). Reanudable: si se corta, vuelve a lanzarlo. Ver kifumaster\README.md.
rem   .\kifu_crawl.bat                 continua el ciclo en curso
rem   .\kifu_crawl.bat --nuevo-ciclo   busca novedades (uso mensual)
cd /d "%~dp0"
python "%~dp0kifumaster\kifu_crawl.py" %*
pause
