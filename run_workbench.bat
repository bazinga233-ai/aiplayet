@echo off
setlocal

set "ROOT=%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\stop-listeners.ps1" -Ports 8001 5173

start "Nova Workbench Backend" cmd /k "cd /d %ROOT% && python -m uvicorn backend.app:app --host 127.0.0.1 --port 8001 --reload"
start "Nova Workbench Frontend" cmd /k "cd /d %ROOT%frontend && npm run dev"
