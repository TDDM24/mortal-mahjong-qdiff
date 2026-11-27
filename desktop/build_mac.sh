#!/bin/bash
# 在 macOS 上把麻将记录打包成 .app（文件夹版，解压即用）
# 用法：  cd 到本目录，然后  bash build_mac.sh
set -e

cd "$(dirname "$0")"
PY=${PYTHON:-python3}

echo "== 1/6 Python 版本 =="
$PY -V

echo "== 2/6 建虚拟环境并装依赖 =="
if [ ! -d .venv ]; then
  $PY -m venv .venv
fi
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "== 3/6 生成 .icns 图标 =="
if [ ! -f mahjong.icns ]; then
  mkdir -p build_icon/mahjong.iconset
  SRC=icons/mahjong_512.png
  [ -f "$SRC" ] || SRC=icons/mahjong.png
  for s in 16 32 128 256 512; do
    sips -z $s $s "$SRC" --out build_icon/mahjong.iconset/icon_${s}x${s}.png >/dev/null
    d=$((s*2))
    sips -z $d $d "$SRC" --out build_icon/mahjong.iconset/icon_${s}x${s}@2x.png >/dev/null
  done
  iconutil -c icns build_icon/mahjong.iconset -o mahjong.icns
fi

echo "== 4/6 PyInstaller 打包（onedir/.app）=="
rm -rf build dist
pyinstaller --noconfirm --clean --windowed \
  --name "麻将记录" \
  --icon mahjong.icns \
  --add-data "icons:icons" \
  --hidden-import openpyxl \
  --osx-bundle-identifier "local.mahjong.record" \
  main_qt.py

echo "== 5/6 ad-hoc 签名（否则 Gatekeeper 可能直接拒绝）=="
codesign --force --deep --sign - "dist/麻将记录.app" || echo "签名失败，可忽略（仍可右键打开）"

echo "== 6/6 打 zip =="
cd dist
ditto -c -k --sequesterRsrc --keepParent "麻将记录.app" "../麻将记录-mac.zip"
cd ..
echo
echo "完成：dist/麻将记录.app  和  麻将记录-mac.zip"
echo "首次运行：右键 → 打开；或执行  xattr -dr com.apple.quarantine 麻将记录.app"
