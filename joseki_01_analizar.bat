@echo off
cd /d "%~dp0"
python generate_joseki_problems.py joseki joseki_problems --dry-run
echo.
echo ===== Donde se pondrian los #ok =====
python generate_joseki_problems.py joseki joseki_problems --dry-run --aceptar-avisos
pause