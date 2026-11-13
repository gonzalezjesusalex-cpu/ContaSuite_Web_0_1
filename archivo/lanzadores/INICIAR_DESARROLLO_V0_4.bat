@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Entorno aislado v0.4. No usa la base ni las carpetas del despacho.
".venv\Scripts\python.exe" scripts\local_v04.py run
pause
