#!/bin/bash
# 双击：在本机起一个小服务器并打开手机界面（浏览器里就能试）
cd "$(dirname "$0")" || exit 1
PORT=8765
PY=$(command -v python3 || echo /usr/bin/python3)
echo "服务器：$PY -m http.server $PORT（目录：$(pwd)）"

# 端口被占就往后换
for p in 8765 8766 8767 8768; do
  if ! lsof -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1; then PORT=$p; break; fi
done

"$PY" -m http.server $PORT --bind 127.0.0.1 >/tmp/mahjong-web.log 2>&1 &
SRV=$!
sleep 1
URL="http://127.0.0.1:$PORT/web/index.html"
echo "打开：$URL"
open "$URL" 2>/dev/null || echo "请手动在浏览器打开上面的地址"
echo
echo "这个窗口不要关；关掉或按 Ctrl+C 就停止服务。"
trap 'kill $SRV 2>/dev/null' INT TERM EXIT
wait $SRV
