@echo off
rem Abre a aplicacao com consola, para ver mensagens de erro.
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Execute primeiro instalar.bat
  pause
  exit /b 1
)
".venv\Scripts\python.exe" app.py
pause
