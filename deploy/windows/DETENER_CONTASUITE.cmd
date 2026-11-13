@echo off
start "" "%~dp0runtime\pythonw.exe" -B "%~dp0app\scripts\local_install.py" --stop "%~dp0."
