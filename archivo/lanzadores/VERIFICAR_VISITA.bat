@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Falta el entorno Python. Ejecuta INICIAR_PRUEBA.bat para prepararlo.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\visit_check.py
pause
