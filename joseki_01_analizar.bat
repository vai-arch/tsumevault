@echo off
cd /d "%~dp0"
python tools\generate_joseki_problems.py joseki joseki_problems --dry-run
echo.
echo ===== Donde se pondrian los #ok =====
python tools\generate_joseki_problems.py joseki joseki_problems --dry-run --aceptar-avisos
pause