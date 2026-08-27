@echo off

start "PLAYER_SAVE_SERVER" cmd /k "title PLAYER_SAVE_SERVER && python .\player\player_save_server.py"

start "SAVE_SERVER" cmd /k "title SAVE_SERVER && python .\tsumevault_server.py"

start "STATIC_SERVER" cmd /k "title STATIC_SERVER && npx serve .."