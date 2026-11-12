@echo off
chcp 65001 >nul
cd /d "%~dp0"
call scripts\bootstrap.bat --portable
if errorlevel 1 goto fin
".venv\Scripts\python.exe" scripts\run_windows.py --portable
:fin
pause
