@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist agent\config.json (
 echo Inicia ContaSuite primero: crea agent\config.json. El agente se vincula al iniciar sesion en ContaSuite
 echo y las carpetas autorizadas se definen en Configuracion, Agentes locales.
 goto fin
)
rem El entorno puede venir de otra PC: no basta con que exista python.exe, debe ejecutarse.
set "PYEXE=.venv\Scripts\python.exe"
"%PYEXE%" -c "import sys" >nul 2>&1
if errorlevel 1 (
 echo El entorno .venv no funciona en este equipo. Reconstruyendolo...
 call scripts\bootstrap.bat
 "%PYEXE%" -c "import sys" >nul 2>&1
)
if errorlevel 1 (
 rem El agente solo usa la biblioteca estandar: respaldo con el lanzador py.
 set "PYEXE=py -3.12"
 py -3.12 -c "import sys" >nul 2>&1
)
if errorlevel 1 (
 echo No se encontro un Python 3.12 utilizable. Instala Python 3.12 de 64 bits con el lanzador py.
 goto fin
)
%PYEXE% agent\agent.py
:fin
pause
