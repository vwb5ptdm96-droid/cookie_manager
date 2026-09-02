@echo off
rem Backend restart script: the backend runs as the Windows service "SessionBackend" (NSSM).
rem Do NOT start uvicorn manually while the service is running, it will conflict on port 8081.
"%~dp0tools\nssm\nssm.exe" restart SessionBackend
