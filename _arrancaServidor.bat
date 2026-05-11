@echo off

start "SAVE_SERVER" cmd /k "title SAVE_SERVER && python .\tsumevault_server.py"

start "STATIC_SERVER" cmd /k "title STATIC_SERVER && npx serve .."