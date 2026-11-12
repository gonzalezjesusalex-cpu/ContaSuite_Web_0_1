@echo off
cd /d "%~dp0.."
py -3 --version >nul 2>&1
if errorlevel 1 (
 echo No se encontro el lanzador py. Instala Python 3.12 de 64 bits con el lanzador.
 exit /b 1
)
py -3 scripts\bootstrap_windows.py %*
exit /b %errorlevel%
