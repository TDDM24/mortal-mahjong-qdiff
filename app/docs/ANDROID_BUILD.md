# 在 Windows 上打包安卓 APK（第 3 阶段）

> 依据：Capacitor 官方文档 <https://capacitorjs.com/docs/getting-started/environment-setup>（2026-11 查过）。
> 我在 Mac 上没有 Android SDK，所以**下面这套流程我没有实际跑过**；第一次跑如果报错，把报错原文发我。

---

## 0. 一次性准备（Windows）

| 装什么 | 版本 | 说明 |
|---|---|---|
| Node.js | **22 或更高** | Capacitor 8 CLI 的 `engines` 要求 `node >= 22`（npm 上 `@capacitor/cli@8.6.3` 里写的） |
| Android Studio | 最新稳定版 | 官方文档：**不用单独装 JDK**，Android Studio 会装它需要的那个 |
| Android SDK | API 34 或 35 | 装完 Android Studio 后在 SDK Manager 里勾上 Platform + Build-Tools |

装完在命令行确认：

```bat
node -v
npm -v
```

---

## 1. 装依赖

把整个项目文件夹拷到 Windows，在项目根目录（有 `package.json` 的那层）执行：

```bat
npm install
```

> ⚠️ npm 12 起默认**不执行依赖的 install script**，装的时候可能悄悄跳过。
> 如果后面 `npx cap sync` 或打包报奇怪的错，先跑一次：

```bat
npx cap doctor
```

> 它会列出被拦下 install script 的包；按提示 `npm install-scripts approve <包名>`，然后 `npm rebuild`。

---

## 2. 生成安卓工程

```bat
npx cap add android
npx cap sync android
```

- `npx cap add android` 会新建 `android/` 目录（Gradle 工程，第一次会自动下 Gradle 和依赖，比较慢）
- 以后每次改了 `web/` 里的东西，只要再跑一次 `npx cap sync android`（它会重新拷贝 `web/` 到 `android/app/src/main/assets/public`）
- 配置在 `capacitor.config.json`：`webDir` 是 `web`，`appId` 是 `com.mahjong.record`，`CapacitorHttp` 已打开

> 如果卡在 Gradle 下载，可以在 `android/gradle/wrapper/gradle-wrapper.properties` 里换成国内镜像，或者用手机热点。

---

## 3. 图标

`assets/icon.png`（1024×1024，由 `icons/mahjong_512.png` 放大而来）已经放好了。生成各尺寸：

```bat
npx @capacitor/assets generate --android
npx cap sync android
```

会写进 `android/app/src/main/res/mipmap-*`。想换图就替换 `assets/icon.png` 再跑一次。

---

## 4. 先跑 debug 版（不用签名，插数据线能装）

```bat
npx cap open android
```

在 Android Studio 里点绿色三角，选真机/模拟器跑。或者在命令行：

```bat
cd android
gradlew.bat assembleDebug
```

产物：`android\app\build\outputs\apk\debug\app-debug.apk`

装到手机（开 USB 调试）：

```bat
adb install -r android\app\build\outputs\apk\debug\app-debug.apk
```

**这一步能跑通，就说明界面、计算、取报告都正常了**，再去做签名版。

---

## 5. 签名（自签名，发给别人装）

### 5.1 生成 keystore（只做一次，**备份好，丢了以后没法覆盖更新**）

```bat
keytool -genkey -v -keystore mahjong.keystore -alias mahjong -keyalg RSA -keysize 2048 -validity 10000
```

会问密码、姓名等，随便填，密码记住。

### 5.2 告诉 Gradle 用这个签名

在 `android/` 下新建 `keystore.properties`：

```properties
storeFile=../mahjong.keystore
storePassword=你的密码
keyAlias=mahjong
keyPassword=你的密码
```

`android/app/build.gradle` 顶部加：

```gradle
def keystoreProperties = new Properties()
def keystorePropertiesFile = rootProject.file('keystore.properties')
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(new FileInputStream(keystorePropertiesFile))
}
```

`android { ... }` 里加：

```gradle
    signingConfigs {
        release {
            if (keystorePropertiesFile.exists()) {
                storeFile file(keystoreProperties['storeFile'])
                storePassword keystoreProperties['storePassword']
                keyAlias keystoreProperties['keyAlias']
                keyPassword keystoreProperties['keyPassword']
            }
        }
    }
    buildTypes {
        release {
            signingConfig signingConfigs.release
            minifyEnabled false
        }
    }
```

> 具体写法随 AGP 版本略有差异；如果 `build.gradle` 已经是 `.kts`（Kotlin DSL），告诉我，我改成 kts 版本。

### 5.3 打包

```bat
cd android
gradlew.bat assembleRelease
```

产物：`android\app\build\outputs\apk\release\app-release.apk`

---

## 6. 装到别人手机上

1. 把 `app-release.apk` 发过去（微信/QQ 传文件会把后缀改掉，让对方改成 `.apk`）
2. 手机上点开 → 允许「安装未知来源应用」
3. 第一次打开会申请网络权限（取报告用）；数据全部存在本机，没有服务器

---

## 7. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| `npx cap add android` 报找不到 SDK | 没装 Android SDK，或 `ANDROID_HOME` 没设。用 Android Studio 的 SDK Manager 装一次，一般会自动配好 |
| Gradle 报 JDK 版本不符 | 用 Android Studio 自带的 JDK（Settings → Build Tools → Gradle → Gradle JDK 选 Embedded JDK） |
| 打包后白屏 | 先 `npx cap sync android`；再看 `web/index.html` 是否是 `webDir` 下的入口。打开手机 Chrome 的 `chrome://inspect` 可以看控制台 |
| 取报告失败 | 浏览器里是 CORS 挡的，APK 里走 CapacitorHttp 应该正常；如果还失败，把界面上的错误文字发我 |
| 安装提示「应用未安装」 | 手机上装过不同签名的同 appId 版本，先卸载旧的 |
| 图标没变 | 跑完 `@capacitor/assets` 后要 `npx cap sync`，再重新打包 |

---

## 8. 我没有验证的部分（明确写出来）

- `npx cap add android` / `cap sync` / Gradle 打包：**没在真机上跑过**，配置是照官方文档写的。
- 图标生成：`@capacitor/assets` 的正确用法我按文档写，但没有跑过实际命令。
- 签名配置片段：随 Android Gradle Plugin 版本会有差异，第一次报错请贴给我。
