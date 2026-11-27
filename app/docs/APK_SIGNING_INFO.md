# APK 签名信息（请备份）

这个 APK 是在 Mac 上打的，用的是自己生成的 keystore。

| 项目 | 值 |
|---|---|
| keystore 文件 | 项目根目录 `mahjong.keystore`（**别丢，别泄漏**） |
| alias | `mahjong` |
| storePassword / keyPassword | 见本机 `android/keystore.properties`（已 gitignore，不写进文档） |
| 有效期 | 10000 天 |
| 证书 SHA-256 | `dc62be21b71a4f1bd08fde9eb3617f2e131c0e0e4e9c884bc4823ec8ff6ed32e` |
| 包名 | `com.mahjong.record` |
| 版本 | 1.0.4（versionCode 5）—— 1.0 → 1.0.1（筛选/分组、SAF 保存）→ 1.0.2（修备份闪退、调试日志）→ 1.0.3（备份 gzip 压缩，单场 728 KB → 39 KB）→ 1.0.4（代码审计修复，见 docs/代码审计修复记录.md） |

## 为什么必须留着

安卓要求「同一个包名的新版本，必须用同一个签名」。keystore 丢了，以后就打不出能覆盖安装的更新版——
只能换个包名重新装，数据不通用（除非先导出备份再导入）。

建议把 `mahjong.keystore` 和这份说明一起放到网盘或者密码管理器里。

## 以后改版本号

`android/app/build.gradle` 里：

```gradle
versionCode 4        // 每次发新版 +1
versionName "1.0.3"  // 给人看的
```

## 1.0.2 修的问题

导出备份 JSON 时闪退、留下 0 字节文件。原因：单场备份就有 728 KB（报告原文占大头），
原来把整段内容当一次插件调用的参数传过去；选文件时应用退到后台，Capacitor 要保存并恢复这个
巨大的待处理调用，容易崩。

改法：`FileSaver` 拆成 `open` / `write` / `close` 三步，JS 每块 32 KB 分块写（`web/js/chunk.js`，
已按 UTF-16 单元切、不切断代理对）。跨桥每次只有 32 KB，token 很小，系统回收后重来也不崩。

同时加了调试日志：原生侧写 `<应用私有目录>/debug.log`，设置页有「导出调试日志」。
出问题时让用户点一下、把 txt 发过来即可。

## 1.0.3：备份改成 gzip

单场备份 728 KB 里，`review`（Mortal 每手候选和 Q 值）占 77%、`mjai_log` 占 20%，都不能删。
所以只压不删：

| 处理 | 大小 |
|---|---|
| 原始（缩进 1 空格） | 728 KB |
| 紧凑 JSON（去掉缩进） | 332 KB |
| 紧凑 + gzip | **39 KB（省 95%）** |

- 导出文件名变成 `麻将记录备份_xxx.json.gz`，用的是浏览器的 `CompressionStream`
  （安卓 WebView 103+ 支持；万一不支持就退回紧凑 JSON，仍是原来的 45%）
- 导入自动识别：看文件头是不是 gzip 魔数 `1f 8b`，是就解压，不是就按普通 JSON 读 —— **旧的 `.json` 备份照样能导**

## 重新打包（这台 Mac 上已经装好工具链）

```bash
cd mahjong-js
npx cap sync android                  # web/ 改过之后必须跑
cd android
export JAVA_HOME="$HOME/.../android-toolchain/jdk-21.0.13.1+2/Contents/Home"
export ANDROID_HOME="$HOME/.../android-toolchain/sdk"
export ANDROID_USER_HOME="$HOME/.../android-toolchain/userhome"
export GRADLE_USER_HOME="$HOME/.../.gradle-home"
./gradlew assembleRelease
```

产物：`android/app/build/outputs/apk/release/app-release.apk`
