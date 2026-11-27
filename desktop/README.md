# 麻将记录 · Mahjong Recorder

给 **Mortal / mjai 复盘报告** 做本地归档与牌效统计的桌面小程序。
粘牌谱链接 → 内嵌浏览器复盘 → 自动抓报告 id → 入库 → 看统计、做牌效审计。

PySide6（Qt）+ SQLite + 内嵌 QtWebEngine，单机运行，不联网上传任何数据。

---

## 功能

- **记录**：粘天凤 / 雀魂牌谱链接（或直接贴 16 位报告 id），点「记录一场」。
  程序会算好 rating、决策数、失分、和了率 / 放铳率等指标写进本地数据库；
  同一份报告重复记录会自动跳过。
- **复盘**：点「复盘」开新标签，内嵌 mjai.ekyu.moe，自动把牌谱链接填进网页输入框；
  你过验证码、提交，报告出来后在地址栏识别 `/report/<id>`，自动回填到记录页。
  可以一次粘多条链接，开多个标签并行。
- **数据**：全表浏览，可搜索、点表头排序（数值列按数值排），双击看单场详情。
  「导入 Excel」可以把旧的历史表一次性搬进库，「导出 Excel」按需生成
  `逐场 / 汇总 / 说明` 三页（会沿用你原表的「汇总」公式）。
- **牌效审计**：勾选若干场，后台批量分类统计
  （该进没进 / 该退没退 / 进张算少 / 宁可少进张 / 改良没看见 / 其他），
  按向听、按类别给出失分分布，并列出「各类最大的几手」。
- **检查点（可选）**：自定义一组维持线 / 检查点，开启后报告里多出两列，
  超线标红、达标标绿；**默认关闭**，不开启时报告里完全不显示这两列。
- **外观**：和风配色，浅色 / 深色 / 跟随系统，设置在 `settings.json`。

## 数据放在哪

程序不依赖 Excel 当数据库，所有记录在 **SQLite** 里：

| 内容 | 位置 |
|---|---|
| 所有记录 | `麻将记录.db` |
| 每场存档 | `程序/牌谱数据/*.md` 和 `*.json`（报告原件） |
| 运行日志 | `程序/logs/app.log`（滚动，1MB × 3） |
| Excel 副本 | 点「导出 Excel」时生成到 `导出/` |
| 设置 | `程序/settings.json` |

数据根目录：

- macOS 打包版：`~/Documents/麻将记录/`
- Windows 打包版：`<exe 所在目录>/`
- 源码运行：仓库根目录
- 可用环境变量 `MAHJONG_HOME=/your/path` 覆盖

> **为什么留 `.md/.json`**：Mortal 的报告链接只保留 15 天，过期后原报告就取不到了。
> 本地存的报告原件是以后还能重新复盘、重新审计的唯一凭据。

## 跑起来（源码）

需要 Python 3.10+（实测 3.12）。

```bash
python -m venv .venv
# macOS / Linux
. .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -r requirements.txt
python main_qt.py
```

## 打包

### macOS

```bash
bash build_mac.sh
```

生成 `dist/麻将记录.app` 和 `麻将记录-mac.zip`（含 ad-hoc 签名）。
细节与注意事项见 [README_MAC.md](README_MAC.md)。

### Windows

```powershell
pyinstaller --noconfirm --windowed --name 麻将记录 ^
  --icon icons\mahjong.ico ^
  --add-data "icons;icons" ^
  --hidden-import openpyxl main_qt.py
```

> 用 **onedir**（上面的默认方式），不要 onefile：onefile 每次启动要把 200MB+ 解压到
> 临时目录，在权限收紧的机器上会报 `Could not create temporary directory!`。

## 测试

```bash
python tests/test_smoke.py
```

可移植自检：在系统临时目录建库 → 插入 → 同 id 去重（大小写/前后空格都算同一条）→
导出 xlsx 并校验三页与行数 → 创建主窗口 → 来回切主题。不依赖任何本机路径，
无头环境（CI）会自动加 `QT_QPA_PLATFORM=offscreen`。

## 设计/实现上的几个取舍

- **SQLite 而不是 Excel 当库**：Excel 会被占用、会有只读属性、会 DDE 唤起失败；
  换 SQLite 后记录是纯本地写入，Excel 只作为导出副本。
- **写库用短连接**：每次操作开连接、用完即关，避免 Windows 上数据库文件被长期占用。
- **序号分配放在 `BEGIN IMMEDIATE` 事务里**，并有 `UNIQUE(seq)` 索引兜底重试，
  防止并发写入拿到同一个序号。
- **报告缓存原子写**：先写 `.part` 再 `os.replace`；解析失败自动删除重下，
  避免一个错误的 HTML 缓存让这场报告永久取不到。
- **耗时操作全部走 QThread**，关窗时询问「等它做完 / 直接关」，不会硬杀线程
  （硬杀会让解释器带着运行中的 QThread 退出，Windows 上是 0xC0000409）。

## 已知限制

- 内嵌网页里的人工验证码得自己过（程序不代做）。
- 牌效审计依赖本地缓存的报告；报告过期且本地没存档的场次会被跳过，并在结果里点名。
- 没有代码签名证书，Windows 首次运行可能弹 SmartScreen，macOS 首次运行需要右键打开。

## 许可

未指定许可证。如果打算公开分发，建议补一个（MIT / Apache-2.0 都合适），
并在 README 顶部加上许可证徽章。

## 致谢

- [Mortal](https://github.com/Equim-chan/Mortal) —— 牌效分析的来源
- [mjai](https://github.com/Equim-chan/mjai) —— 报告站点 `mjai.ekyu.moe`
