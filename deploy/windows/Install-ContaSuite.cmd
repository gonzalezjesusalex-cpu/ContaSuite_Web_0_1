@echo off
setlocal
if "%~1"=="" goto usage
if "%~2"=="" goto usage
if /I "%~3"=="Install" goto install
if /I "%~3"=="Update" goto update
:usage
echo Uso: Install-ContaSuite.cmd "python.exe" "datos absolutos" Install^|Update ["respaldo verificado"]
exit /b 2
:install
"%~1" -B "%~dp0..\..\scripts\schema_admin.py" --data-dir "%~2" --apply --new
exit /b %errorlevel%
:update
if "%~4"=="" goto usage
"%~1" -B "%~dp0..\..\scripts\schema_admin.py" --data-dir "%~2" --apply --backup "%~4"
exit /b %errorlevel%
