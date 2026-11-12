@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Cuenta de laboratorio: devadmin. La contraseña no se mostrara ni se guardara en texto plano.
".venv\Scripts\python.exe" scripts\local_v04.py password
pause
