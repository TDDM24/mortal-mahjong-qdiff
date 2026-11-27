@echo off
rem 在 Windows 上把「麻将记录」打包成 exe（onedir，解压即用）
rem 用法：双击本文件，或者在这个目录里执行  build_win.bat
setlocal
cd /d "%~dp0"

echo == 1/5 检查 Python ==
where python >nul 2>nul
if errorlevel 1 (
  echo 没找到 python。装一个 Python 3.12（勾选 Add to PATH）再试。
  pause
  exit /b 1
)

echo == 2/5 建虚拟环境并装依赖 ==
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install --upgrade pip
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 ( echo 依赖安装失败 & pause & exit /b 1 )

echo == 3/5 生成图标 ==
if not exist "mahjong.ico" (
  .venv\Scripts\python.exe -c "from PIL import Image; Image.open('icons/mahjong_512.png').save('mahjong.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])" 2>nul
  if errorlevel 1 echo [提示] 没装 Pillow，跳过图标，用默认图标
)

echo == 4/5 PyInstaller 打包 ==
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist
set "ICON="
if exist "mahjong.ico" set "ICON=--icon mahjong.ico"
.venv\Scripts\pyinstaller.exe --noconfirm --clean --windowed --name "麻将记录" %ICON% --add-data "icons;icons" --hidden-import openpyxl main_qt.py
if errorlevel 1 ( echo 打包失败 & pause & exit /b 1 )

echo == 5/5 打 zip ==
if exist "麻将记录-win.zip" del "麻将记录-win.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\麻将记录\*' -DestinationPath '麻将记录-win.zip' -Force"
powershell -NoProfile -Command "Compress-Archive -Path 'mahjong.ico' -DestinationPath '麻将记录-win.zip' -Update" >nul 2>nul

echo.
echo 完成：
echo   dist\麻将记录\麻将记录.exe   （可直接双击运行）
echo   麻将记录-win.zip             （发给别人用，解压即用）
echo.
echo 请把 dist\麻将记录 整个目录 和 麻将记录-win.zip 一起提交到 mahjong\releases\ 下。
pause
