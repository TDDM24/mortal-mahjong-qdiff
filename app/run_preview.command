#!/bin/bash
# 双击：把这份测试报告渲染成 HTML 并用浏览器打开（看排版和内容对不对）
cd "$(dirname "$0")" || exit 1
NODE=""
for c in "$(command -v node 2>/dev/null)" \
         "$HOME"/.dsh/dsh-runtimes/*/dependencies/node/bin/node \
         /opt/homebrew/bin/node /usr/local/bin/node /usr/bin/node; do
  if [ -n "$c" ] && [ -x "$c" ]; then NODE="$c"; break; fi
done
if [ -z "$NODE" ]; then echo "没找到 Node，先看 run_test.command 里的说明。"; read -n 1 -s -r -p "按任意键关闭。" || true; exit 1; fi
"$NODE" test/preview.js web/data/report_0b0d6c2336b144eb.json
F=$(ls -t 预览_*.html | head -1)
open "$F" 2>/dev/null || echo "文件在这里：$(pwd)/$F"
sleep 1
