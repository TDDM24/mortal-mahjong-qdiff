@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 目录：%CD%
echo.
where node >nul 2>nul
if errorlevel 1 (
  echo 没找到 Node。请先装 https://nodejs.org 的 LTS 版本，装完重开这个窗口再双击本文件。
  pause
  exit /b 1
)
for /f "delims=" %%v in ('node -v') do echo Node：%%v
echo.
node test\test_golden.js web\data\report_0b0d6c2336b144eb.json
echo.
pause
