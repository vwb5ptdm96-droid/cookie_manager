@echo off
setlocal
REM Interactive-session backend launcher (task: SessionBackend-Interactive).
REM Runs in the interactive session so headful Chrome windows are visible.
set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"
REM Prefer backend\.venv (has alembic/pymysql etc), fall back to system python.
if exist "%ROOT_DIR%backend\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT_DIR%backend\.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe"
)
REM App logs are written by run_server.py to runtime/logs/backend.log (rotated).
REM Keep stdout/stderr in boot.log for early-startup diagnostics.
"%PYTHON_EXE%" "%ROOT_DIR%run_server.py" >> "%ROOT_DIR%runtime\logs\boot.log" 2>&1
