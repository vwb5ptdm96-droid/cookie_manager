@echo off
setlocal
REM Interactive-session backend launcher (replaces NSSM service SessionBackend).
REM Runs in the user's interactive session so headful Chrome windows are visible.
set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"
set "PYTHON_EXE=C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe"
if not exist "%ROOT_DIR%runtime\logs" mkdir "%ROOT_DIR%runtime\logs"
"%PYTHON_EXE%" "%ROOT_DIR%run_server.py" >> "%ROOT_DIR%runtime\logs\backend-interactive.log" 2>&1
