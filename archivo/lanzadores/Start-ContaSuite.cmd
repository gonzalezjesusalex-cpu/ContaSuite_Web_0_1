@echo off
setlocal
if "%~1"=="" exit /b 2
if "%~2"=="" exit /b 2
set "csRecoveryMode=%~3"
set "csRecoveryPort=%~4"
if "%csRecoveryMode%"=="" set "csRecoveryMode=api"
if "%csRecoveryPort%"=="" set "csRecoveryPort=8000"
"%~1" -B "%~dp0..\..\scripts\service_runtime.py" --data-dir "%~2" --mode "%csRecoveryMode%" --port "%csRecoveryPort%"
exit /b %errorlevel%
