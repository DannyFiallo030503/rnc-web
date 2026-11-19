@echo off
setlocal
cd /d "%~dp0"
title RNC - Consulta local
"%~dp0runtime\python.exe" "%~dp0launcher.py"
if errorlevel 1 (
  echo.
  echo Si RNC ya esta abierto, utilice su ventana anterior.
  echo Si no, copie el mensaje de error para solicitar ayuda.
  pause
)
