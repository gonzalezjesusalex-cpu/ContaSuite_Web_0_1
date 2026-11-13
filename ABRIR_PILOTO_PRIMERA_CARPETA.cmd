@echo off
chcp 65001 >nul
cd /d "%~dp0"
".venv\Scripts\python.exe" -B scripts\pilot_first.py open
if errorlevel 1 goto failed
echo.
echo Acceso privado: .qa\pilot-first\access.json
echo Empresas - Importar y conciliar - Fuente - Primera carpeta: analisis por lotes
start "" "http://127.0.0.1:8062/empresas?tab=Importar%%20y%%20conciliar"
goto end
:failed
echo No fue posible abrir el piloto. No se ejecutaron migraciones ni importaciones.
:end
pause
