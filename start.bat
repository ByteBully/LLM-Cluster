@echo off
cd /d "%~dp0"
py -3 -c "import PySide6" 2>nul
if errorlevel 1 (
  echo Installing PySide6...
  py -3 -m pip install -r requirements.txt
  if errorlevel 1 (pause & exit /b 1)
)
py -3 app.py
if errorlevel 1 pause
