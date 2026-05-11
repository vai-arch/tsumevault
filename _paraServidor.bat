@echo off

echo Parando servidores en puertos 3000 y 3002...

for %%p in (3000 3002) do (
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr :%%p') do (
        taskkill /PID %%a /F
    )
)
