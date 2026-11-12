@echo off
chcp 65001 >nul
cd /d "%~dp0backend"
if not exist "..\.venv\Scripts\python.exe" (
  echo Primero prepara el entorno con INICIAR_PRUEBA.bat.
  pause
  exit /b 1
)
echo CS-Storage: indexador de solo lectura. Ctrl+C para detener.
"..\.venv\Scripts\python.exe" -m app.storage.worker
pause
