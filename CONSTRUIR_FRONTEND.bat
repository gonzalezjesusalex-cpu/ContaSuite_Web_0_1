@echo off
cd /d "%~dp0frontend"
call npm ci
if errorlevel 1 goto fin
call npm run build
if errorlevel 1 goto fin
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" ".venv\Scripts\python.exe" scripts\stamp_build.py
:fin
pause
