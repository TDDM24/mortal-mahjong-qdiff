# macOS 版（原生壳 + 同一套网页）

产物：`麻将记录.app`（2.9 MB）。界面和安卓版是**同一份 `web/`**，不用分开维护。

## 为什么不用 Electron

Electron 也能打包，但一个空壳就要 200 MB 以上，还要额外装依赖。这台机器自带 Swift 工具链，
写一个 WKWebView 外壳只要 150 KB 二进制，**整套 2.9 MB**，冷启动也快得多。

## 结构

```
mac/
├── main.swift          原生壳：窗口 + WKWebView + 内置 HTTP 服务（约 500 行）
├── Info.plist          Bundle 信息（标识 com.mahjong.record.mac）
└── build_mac.command   双击：编译 → 组装 .app → 生成图标 → 自签名
```

壳内起一个只监听 `127.0.0.1:48623` 的小服务：

| 路径 | 作用 |
|---|---|
| `GET /…` | 静态文件（`Contents/Resources/web`） |
| `GET /report/<16位id>.json` | 代理到 `mjai.ekyu.moe`，网页发的是**同源请求**，所以没有 CORS 问题 |
| `POST /save` | 弹系统「存储为…」，把内容写到用户选的位置（替代安卓的 SAF） |
| `GET /health` | 单实例检测用 |

网页端只加了两个判断，别的没动：

- `net.js`：`window.MJ_MAC` 为真时，取报告的地址从 `https://mjai.ekyu.moe/report/` 换成 `/report/`
- `app.js`：`window.MJ_MAC` 为真时，保存文件改成 `POST /save`

`window.MJ_MAC` 是壳在页面加载前注入的，所以浏览器、安卓 APK 的行为完全不受影响。

## 数据存在哪

`~/Library/WebKit/com.mahjong.record.mac`（WKWebView 的 IndexedDB）。备份用设置页的
「导出备份 JSON」，和安卓版通用（gzip 的 `.json.gz` 两边都能导）。

**端口是固定的**，因为 IndexedDB 按 origin（含端口）隔离。如果 48623 被别的程序占了，
app 会直接弹窗提示而不是换端口——换了端口就会看不到以前的记录。

## 已验证 / 没验证

已验证（这台机器上跑的）：

- 编译、组装、自签名、图标
- 启动后 `/health`、静态文件、**代理真实取到报告**（433 KB，能解析）
- WKWebView 正常渲染、IndexedDB 能存示例数据、列表页/详情页排版正常（宽屏收成 780px 一列）
- 单实例：重复启动第二个会自动退出
- zip 打包→解压→重跑，正常

没验证：

- `POST /save` 的「存储为…」对话框（需要人点，我在无头环境点不了）
- 删除/清空时的确认框（WKWebView 默认不弹 JS 对话框，我在 `WKUIDelegate` 里实现了原生弹窗，但没点过）

## 分发

拷给别人时 zip 会带上「来自网络」标记，对方第一次要右键 → 打开。要免这一步得用开发者证书签名 + 公证。
