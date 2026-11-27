# 麻将记录 · macOS 编译说明

给 Mac 上的 AI / 你自己照做即可。

## 一、这个目录是什么

Qt 版麻将记录（PySide6 + SQLite + 内嵌 QtWebEngine）。Windows 上已经跑通，源码与平台无关；只有打包脚本和少数路径按平台分支。

```
main_qt.py        主窗口（记录 / 数据 / 复盘多标签）
core.py           业务层：取报告、计算、HTML、日志、路径
store.py          SQLite 存储 + Excel 导入导出
mr.py             Mortal 报告解析与指标计算
fastsh.py         向听数
effaudit.py       牌效分类
ui/theme.py       E 和风主题（浅/深/跟随系统）
ui/review.py      内嵌浏览器复盘页
icons/            应用图标
tests/            自测（可在 Mac 上跑）
build_mac.sh      一键打包
requirements.txt
```

## 二、编译（两条命令）

```bash
cd <这个目录>
bash build_mac.sh
```

脚本会：建 venv → 装依赖 → 用 icons/ 生成 .icns → PyInstaller 打成 `dist/麻将记录.app` → ad-hoc 签名 → 打 `麻将记录-mac.zip`。

要求：macOS 11+，Python 3.10+（推荐 3.12），Xcode Command Line Tools（`xcode-select --install`）。

## 三、首次运行

```bash
xattr -dr com.apple.quarantine dist/麻将记录.app
open dist/麻将记录.app
```
或者右键 →「打开」→ 仍要打开。

## 四、数据放在哪

Mac 上（打包版）自动用 `~/Documents/麻将记录/`：

```
~/Documents/麻将记录/
├─ 麻将记录.db          SQLite，所有记录
├─ 麻将逐场数据.xlsx    可选：首次启动自动导入的老表
├─ 程序/logs/app.log    运行日志
└─ 程序/牌谱数据/       每场 .md + 报告原件 .json（报告 15 天过期，靠这个留档）
```

想换位置：启动前设环境变量 `MAHJONG_HOME=/your/path`（macOS 上如果从 Finder 双击，用 `launchctl setenv MAHJONG_HOME /your/path` 或包一层脚本）。

## 五、Mac 上的注意事项（Windows 版踩过的坑，别重犯）

1. **QtWebEngine**：.app 里要能加载 QtWebEngineProcess 与 resources；PyInstaller 6 的 PySide6 hook 一般能处理。若内嵌网页白屏，检查
   `dist/麻将记录.app/Contents/Frameworks/PySide6/Qt/lib/QtWebEngineCore.framework` 是否存在，以及
   `Contents/Resources/PySide6/resources`、`translations/qtwebengine_locales` 是否被打进去（Windows 版就是靠显式指定这两个路径解决的，代码在 main_qt.py 顶部）。
2. **签名**：ad-hoc（`--sign -`）能过 Gatekeeper 的「无法验证开发者」，但每次重打包都要重新签；`--deep` 只是图省事。
3. **架构**：Intel / Apple Silicon 分开打包（PyInstaller 不做通用二进制）。在 M 系机器上打出来就是 arm64。
4. **不弹黑框**：Mac 上 `.app` 本来就是无控制台的，不用管 Windows 那套 SmartScreen/解除锁定。
5. **路径分隔符**：代码里统一用 `os.path.join`；Excel 导出走 `.tmp` + `os.replace`，跨平台可用。
6. **测试**：

```bash
. .venv/bin/activate
export QT_QPA_PLATFORM=offscreen        # 无头跑 GUI 测试时需要
python tests/test_core.py
python tests/test_record_flow.py
```
   `test_record_flow.py` 里写的临时目录是 Windows 路径（`D:\...`），Mac 上改成本地路径或直接跳过；`test_core.py` 与 `test_audit_ui.py` 依赖 `D:\DSH\mahjong-test\reports` 缓存，也需要改路径。

## 六、自检

```bash
. .venv/bin/activate
python tests/test_smoke.py          # 不需要任何外部数据，临时目录里跑完整链路
```

## 七、已知未做（Mac 侧可自行决定）

- 检查点（维持线/检查点）默认关闭，开关存在 `settings.json` 的 `lines_on`。
- 牌效审计依赖本地缓存的报告 JSON（`程序/牌谱数据/*.json`），报告过期且无缓存会跳过并在结果里点名。
- 没有代码签名证书，属于自用/小范围分发。