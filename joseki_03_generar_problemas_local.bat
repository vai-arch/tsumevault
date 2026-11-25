@echo off
cd /d "%~dp0"
python tools\generate_joseki_problems.py joseki joseki_problems
pause