@echo off
rem AR1: construye kifumaster\data\archive.db y las listas games.txt desde kifumaster\data\raw\ (sin red).
cd /d "%~dp0"
python "%~dp0kifumaster\kifu_build.py"
pause
