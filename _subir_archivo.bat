@echo off
rem AR2: sube al VPS los SGF nuevos de archive\sgf\ y kifumaster\data\archive.db si ha cambiado
rem (sustitucion atomica; nunca borra nada en el servidor). Ver kifumaster\README.md.
rem   .\_subir_archivo.bat             sube
rem   .\_subir_archivo.bat --simular   solo ensena lo que haria
cd /d "%~dp0"
python "%~dp0kifumaster\kifu_upload.py" %*
pause
