#!/bin/bash
# 双击这个文件即可跑第 1 阶段验收（macOS）。它会自己找 Node，不需要你配环境变量。
cd "$(dirname "$0")" || exit 1
echo "目录：$(pwd)"
echo

NODE=""
for c in "$(command -v node 2>/dev/null)" \
         "$HOME"/.dsh/dsh-runtimes/*/dependencies/node/bin/node \
         /opt/homebrew/bin/node /usr/local/bin/node /usr/bin/node; do
  if [ -n "$c" ] && [ -x "$c" ]; then NODE="$c"; break; fi
done

if [ -z "$NODE" ]; then
  echo "没找到 Node。两种办法："
  echo "  1) 装一个：https://nodejs.org 下载 LTS 的 .pkg，装完再双击本文件"
  echo "  2) 如果装过 DeepSeek Harness，它自带 Node，路径一般是："
  echo "     ~/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/node/bin/node"
  echo
  read -n 1 -s -r -p "按任意键关闭。" || true
  exit 1
fi

NODEVER=$("$NODE" -v 2>/dev/null)
printf 'Node：%s（%s）\n' "$NODE" "$NODEVER"
echo
"$NODE" test/test_golden.js web/data/report_0b0d6c2336b144eb.json
CODE=$?
echo
if [ $CODE -eq 0 ]; then
  echo "✅ 第 1 阶段通过：计算核心和 golden 完全一致。"
else
  echo "❌ 有不一致（见上面列出的字段）。把这整段输出复制发我。"
fi
echo
read -n 1 -s -r -p "按任意键关闭这个窗口。" || true
exit 0
