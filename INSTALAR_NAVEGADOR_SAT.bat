@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Instala Playwright y el Firefox propio del agente para la descarga de declaraciones del SAT.
rem No toca el .env, data\ ni ninguna instancia. Descarga Firefox (unos 100 MB) de la fuente oficial de Playwright.
rem Usa el mismo Python que INICIAR_AGENTE.bat.
set "PYEXE=.venv\Scripts\python.exe"
"%PYEXE%" -c "import sys" >nul 2>&1
if errorlevel 1 (
 set "PYEXE=py -3.12"
 py -3.12 -c "import sys" >nul 2>&1
)
if errorlevel 1 (
 echo No se encontro un Python 3.12 utilizable. Instala Python 3.12 de 64 bits con el lanzador py.
 goto fin
)
set "PLAYWRIGHT_BROWSERS_PATH=%LOCALAPPDATA%\ContaSuite\agent\playwright-browsers"
%PYEXE% -m pip install -r agent\requirements-sat.txt
if errorlevel 1 goto error
%PYEXE% -m playwright install firefox
if errorlevel 1 goto error
echo.
echo Firefox del agente listo en %PLAYWRIGHT_BROWSERS_PATH%
%PYEXE% scripts\sat_preflight.py
goto fin
:error
echo No se pudo instalar. Revisa la conexion a Internet y vuelve a intentar.
:fin
pause
