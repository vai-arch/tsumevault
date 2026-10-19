@echo off
cd /d "%~dp0"
python generate_joseki_problems.py joseki joseki_problems
pause