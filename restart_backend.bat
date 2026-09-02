@echo off
rem Restart backend via the interactive-session scheduled task (SessionBackend-Interactive).
rem 1) kill whatever holds port 8081  2) end any lingering task instance  3) re-trigger the task
setlocal
set "PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8081 ^| findstr LISTENING') do (
    if not defined PID set "PID=%%a"
)
if defined PID (
    echo Killing backend process PID %PID% ...
    taskkill /pid %PID% /f
)
echo Ending lingering task instance (if any) ...
schtasks /end /tn SessionBackend-Interactive
ping -n 4 127.0.0.1 >nul
echo Re-triggering task SessionBackend-Interactive ...
schtasks /run /tn SessionBackend-Interactive
