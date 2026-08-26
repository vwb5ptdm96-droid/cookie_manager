@echo off
setlocal

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

if exist ".env" (
    for /f "usebackq eol=# tokens=1* delims==" %%A in (`findstr /R "^[A-Za-z_][A-Za-z0-9_]*=" ".env"`) do (
        if not defined %%A set "%%A=%%B"
    )
)

if not defined APP_HOST set "APP_HOST=0.0.0.0"
if not defined APP_PORT set "APP_PORT=8081"
if not defined DEPLOY_ROOT set "DEPLOY_ROOT=%ROOT_DIR:~0,-1%"
if not defined RUNTIME_ROOT set "RUNTIME_ROOT=%ROOT_DIR%runtime"

if exist "%ROOT_DIR%backend\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT_DIR%backend\.venv\Scripts\python.exe"
) else if exist "%ROOT_DIR%.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT_DIR%.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

if not exist "%RUNTIME_ROOT%" mkdir "%RUNTIME_ROOT%"
if not exist "%RUNTIME_ROOT%\profiles" mkdir "%RUNTIME_ROOT%\profiles"
if not exist "%RUNTIME_ROOT%\scripts" mkdir "%RUNTIME_ROOT%\scripts"
if not exist "%RUNTIME_ROOT%\artifacts" mkdir "%RUNTIME_ROOT%\artifacts"
if not exist "%RUNTIME_ROOT%\logs" mkdir "%RUNTIME_ROOT%\logs"
if not exist "%RUNTIME_ROOT%\cache" mkdir "%RUNTIME_ROOT%\cache"

echo [1/2] Running alembic migrations...
pushd "backend"
"%PYTHON_EXE%" -m alembic -c "alembic.ini" upgrade head
set "MIGRATION_EXIT=%ERRORLEVEL%"
popd
if not "%MIGRATION_EXIT%"=="0" exit /b %MIGRATION_EXIT%

if /I "%~1"=="--migrate-only" (
    echo Migration finished.
    exit /b 0
)

echo [2/2] Starting backend server...
"%PYTHON_EXE%" -m uvicorn app.main:app --host "%APP_HOST%" --port "%APP_PORT%" --app-dir "backend"
