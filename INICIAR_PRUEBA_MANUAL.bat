@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Prueba manual con datos sinteticos en %LOCALAPPDATA%\ContaSuite\prueba-manual (no usa .env ni data\).
rem Reconstruye el .venv si viene de otra PC y lo prepara con las dependencias base (incluye OCR e icono del agente).
call scripts\bootstrap.bat --portable
if errorlevel 1 goto fin
".venv\Scripts\python.exe" scripts\manual_trial.py %*
:fin
pause
