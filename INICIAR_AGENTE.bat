@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist agent\config.json (
 echo Inicia ContaSuite primero. Despues revisa agent\config.json para autorizar tus carpetas.
 goto fin
)
if not exist ".venv\Scripts\python.exe" (
 echo Primero ejecuta INICIAR_CONTASUITE.bat o INICIAR_PRUEBA.bat.
 goto fin
)
".venv\Scripts\python.exe" agent\agent.py
:fin
pause
