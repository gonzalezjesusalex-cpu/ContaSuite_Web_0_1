@echo off
setlocal
if "%~1"=="" exit /b 2
"%~dp0runtime\python.exe" -B "%~dp0app\scripts\service_runtime.py" --data-dir "%~1"
exit /b %errorlevel%
