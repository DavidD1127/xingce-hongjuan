@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

set "PY="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY if exist "D:\Python310\python.exe" set "PY=D:\Python310\python.exe"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo 没找到 Python，装一个 3.8 以上的版本再双击我。
  pause
  exit /b 1
)

if not exist hongjuan.db (
  echo 第一次运行，正在从题库生成数据库……
  "%PY%" build_db.py
  if errorlevel 1 (
    echo 生成失败，检查 D:\AI\xingcezhenti 在不在。
    pause
    exit /b 1
  )
)

echo 服务在 http://127.0.0.1:8400 ，关掉这个窗口就停了。
start "" "http://127.0.0.1:8400"
"%PY%" server.py
pause
