@echo off
setlocal
"%~dp0runtime\python.exe" -B "%~dp0app\scripts\install_release.py" %*
exit /b %errorlevel%
