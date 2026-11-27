@echo off
rem 在 Windows 上把「麻将记录」打包成 exe（onedir，解压即用）
rem 用法：双击本文件，或者在这个目录里执行  build_win.bat
rem 说明：不需要 Python 在 PATH 里，脚本会自己找（python / py -3 / 常见安装路径）
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo == 1/6 找 Python ==
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY ( where py >nul 2>nul && set "PY=py -3" )
if not defined PY (
  for %%D in ("%LOCALAPPDATA%\Programs\Python\Python312" "%LOCALAPPDATA%\Programs\Python\Python311" "C:\Python312" "C:\Python311") do (
    if exist "%%~D\python.exe" if not defined PY set "PY=%%~D\python.exe"
  )
)
if not defined PY (
  echo 没找到 Python。
  echo   1^) 装一个 Python 3.12：https://www.python.org/downloads/windows/
  echo   2^) 装的时候勾上 "Add python.exe to PATH"
  echo   3^) 或者把已有的 Python 目录加进 PATH，再重跑本脚本
  pause
  exit /b 1
)
echo    用：%PY%
%PY% -c "import sys;print('   版本',sys.version.split()[0])"

echo == 2/6 建虚拟环境并装依赖 ==
if not exist ".venv\Scripts\python.exe" (
  %PY% -m venv .venv
  if errorlevel 1 ( echo 建虚拟环境失败 & pause & exit /b 1 )
  .venv\Scripts\python.exe -m pip install --upgrade pip -q
)
.venv\Scripts\python.exe -m pip install -q -r requirements.txt
if errorlevel 1 ( echo 依赖安装失败 & pause & exit /b 1 )

echo == 3/6 跑自检（五项指标必须和 golden 一致）==
.venv\Scripts\python.exe -c "import json,mr;s=mr.summary(mr.analyze(json.load(open('reports/0b0d6c2336b144eb.json',encoding='utf-8'))));print('   合计失分 %.4f 严重失误 %.4f' % (s['loss'], s['severe']))"
if errorlevel 1 ( echo 自检失败，先别打包 & pause & exit /b 1 )

echo == 4/6 生成图标 ==
if not exist "mahjong.ico" (
  .venv\Scripts\python.exe -c "from PIL import Image; Image.open('icons/mahjong_512.png').save('mahjong.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])" 2>nul
  if errorlevel 1 echo [提示] 没装 Pillow，跳过图标，用默认图标
)

echo == 5/6 PyInstaller 打包 ==
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist
set "ICON="
if exist "mahjong.ico" set "ICON=--icon mahjong.ico"
.venv\Scripts\pyinstaller.exe --noconfirm --clean --windowed --name "麻将记录" %ICON% --add-data "icons;icons" --hidden-import openpyxl main_qt.py
if errorlevel 1 ( echo 打包失败 & pause & exit /b 1 )

echo == 6/6 打 zip ==
if exist "麻将记录-win.zip" del "麻将记录-win.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\麻将记录\*' -DestinationPath '麻将记录-win.zip' -Force"
if errorlevel 1 ( echo 压缩失败 & pause & exit /b 1 )

echo.
echo 完成：
echo   dist\麻将记录\麻将记录.exe   直接双击就能跑
echo   麻将记录-win.zip             发给别人 / 传 GitHub Releases 用
echo.
echo 发之前确认四件事：
echo   1. 标题栏显示  麻将记录 v1.0.0
echo   2. 粘一场三麻牌谱，应提示「这场是 3 人麻将，当前版本只支持四麻」
echo   3. 导出 Excel 后，没防守样本的场次「每100次防守决策」是空格子，不是 #VALUE!
echo   4. 备注以 = 开头的场次，导出后 Excel 里显示纯文本，不执行公式
echo.
echo 产物不要提交进 Git（.gitignore 已挡住），传到 GitHub Releases
pause
