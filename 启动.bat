@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"

set "PY="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY if exist "D:\Python310\python.exe" set "PY=D:\Python310\python.exe"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo [ERROR] Python not found. Install Python 3.8+ and run again.
  pause
  exit /b 1
)

if not exist hongjuan.db (
  echo [INFO] First run: building database from the question bank...
  "%PY%" build_db.py
  if errorlevel 1 (
    echo [ERROR] Build failed. Check the question bank folder.
    pause
    exit /b 1
  )
)

echo [INFO] HongJuan running at http://127.0.0.1:8400
echo [INFO] Keep this window OPEN. Closing it stops the server.
echo.
start "" "http://127.0.0.1:8400"

:run
"%PY%" -u server.py
echo.
echo [INFO] Server exited. Restarting in 3 seconds. Close this window to stop.
ping -n 4 127.0.0.1 >nul
goto run
