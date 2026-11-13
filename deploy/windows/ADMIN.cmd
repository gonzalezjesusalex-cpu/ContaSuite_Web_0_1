@echo off
"%~dp0runtime\python.exe" -B "%~dp0app\scripts\service_admin.py" --status --name ContaSuiteApi
echo.
echo Administracion: app\docs\INSTALL_RC1.md
echo Acceso LAN: usar el nombre HTTPS configurado por el administrador.
pause
