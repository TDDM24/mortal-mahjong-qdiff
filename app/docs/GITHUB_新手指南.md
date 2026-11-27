# GitHub 新手指南（macOS，零基础）

目标：把这个项目传到 GitHub，以后能持续更新。全程用图形界面，不用命令行。

预计第一次需要 20 分钟。

---

## 第 0 步：先确认这几件事（已经帮你做好了）

| 检查项 | 状态 |
|---|---|
| 排除 `node_modules`（100 MB） | ✅ 已写进 `.gitignore` |
| 排除 `android/build` 等构建产物 | ✅ |
| **排除签名文件**（`*.keystore`、`keystore.properties`） | ✅ **最关键，里面有密码** |
| 排除原始牌谱、报告、日志 | ✅ |
| 许可证 | ✅ MIT（`LICENSE`） |
| README | ✅ 已写好 |

> ⚠️ **签名文件绝对不能上传。** 别人拿到它就能冒充你发布 App 更新。
> 万一误传：立刻删仓库 → 重新生成 keystore → 改密码（见 `docs/APK_SIGNING_INFO.md`）。

---

## 第 1 步：注册 GitHub 账号

1. 打开 <https://github.com/signup>
2. 填邮箱 → 密码 → 用户名（英文，会成为网址的一部分，例如 `beitaijun`）
3. 验证邮箱

免费账号足够（公开仓库无限、私有仓库也免费，有 1 GB 软限制）。

---

## 第 2 步：装 GitHub Desktop（推荐，不用敲命令）

1. 打开 <https://desktop.github.com/> → Download for macOS
2. 双击下载的 `.dmg`，把图标拖到 Applications
3. 第一次打开如果提示「无法验证开发者」：
   系统设置 → 隐私与安全性 → 拉到底 → 「仍要打开」
4. 启动后选 **Sign in to GitHub.com**，用第 1 步的账号登录

> 为什么用 Desktop 而不是命令行？它会自动处理登录凭据、显示改动了哪些文件、
> 避免你敲错命令把不该传的东西推上去。

---

## 第 3 步：把本地项目加进来

1. 菜单 **File → Add Local Repository…**
2. 点 **Choose…**，选择这个文件夹：

   ```
   /Users/zhangyouyang/Documents/deepseek-harness/default-workspace/mahjong-js
   ```

3. 它会提示「这不是一个 Git 仓库」——点 **create a repository**（我们初始化过，但没提交）

   > 如果直接看到了 Changes 列表，说明已经被识别，跳过这步。

4. 左边栏会出现仓库名 `mahjong-js`，右边是 **Changes** 标签页

---

## 第 4 步：检查文件列表（重要）

在 Changes 里**逐个扫一眼**，确认：

- ✅ 有 `README.md`、`LICENSE`、`.gitignore`、`web/`、`test/`、`research/`、`docs/`
- ✅ 有 `android/app/src/...` 这类源代码
- ❌ **不能有** `mahjong.keystore`
- ❌ **不能有** `android/keystore.properties`
- ❌ 不能有 `node_modules/`、`android/build/`

如果看到了不该有的文件：先不要提交，把它从列表里排除，
或者回到我在 `.gitignore` 里加一行（告诉我文件名即可）。

确认无误后：

1. 左下角 **Summary** 填一句：`初始提交：麻将记录 Q 差统计与复盘`
2. 点 **Commit to main**

---

## 第 5 步：发布到 GitHub

1. 顶部会出现 **Publish repository** 按钮，点它
2. 填写：
   - **Name**：`mahjong-qdiff`（或你喜欢的名字，英文）
   - **Description**：`把 Mortal 的逐手 Q 差聚合成可检验的五项指标，附统计研究`
   - **Keep this code private**：
     - 想公开 → **取消勾选**
     - 只想自己看 → 勾上（以后随时能改）
3. 点 **Publish repository**

完成后：**Repository → View on GitHub** 就能在浏览器里看到你的仓库了。

网址形如 `https://github.com/你的用户名/mahjong-qdiff`。

---

## 第 6 步：之后怎么更新

每次改了文件：

1. 打开 GitHub Desktop，仓库会自动显示改动
2. 在 **Summary** 写一句这次改了什么（例如「补充第 5 轮分析」）
3. 点 **Commit to main**
4. 点右上角 **Push origin**

> Commit 是「存到本地」，Push 是「传到网上」。两步都要做。

---

## 第 7 步：在网页上能做什么

| 想做的事 | 位置 |
|---|---|
| 改 README（在线编辑） | 仓库首页 → 文件右上角铅笔图标 → Commit changes |
| 发布 APK 给别人下载 | 右侧 **Releases** → **Create a new release** → 上传 `.apk` |
| 收反馈 / 记待办 | **Issues** → New issue |
| 打标签分类 | 首页右侧 **About** 旁的齿轮 → Topics（如 `mahjong` `mortal` `statistics`） |

> APK 不要直接放进仓库（每次更新都会让仓库翻倍），放 **Releases** 里，每个版本一个。

---

## 常见问题

**Q：提示文件太大（超过 100 MB）怎么办？**
说明有构建产物没被排除。检查 `.gitignore` 是否包含 `node_modules/`、`android/build/`。
如果真的需要传大文件，用 Releases 附件（单个最大 2 GB）。

**Q：提交后发现有密码文件传上去了？**
1. 立刻在 GitHub 网页删掉那个文件并提交
2. 但历史记录里还在 → 换密码/重新生成密钥
3. 简单粗暴但有效的办法：删掉整个仓库重建

**Q：想改仓库名？**
Repository → Settings → Rename。

**Q：想公开成开源项目？**
Settings → 最下面 Danger Zone → Change visibility → Public。

**Q：多人协作怎么办？**
本项目目前是单人。以后有人要一起改：Settings → Collaborators → Add people。

**Q：命令行版怎么用？**
```bash
git add -A
git commit -m "说明"
git push
```
但新手用 Desktop 就够了。

---

## 一句话总结

1. 装 GitHub Desktop，登录
2. Add Local Repository → 选 `mahjong-js`
3. 确认没有 keystore → Commit to main
4. Publish repository
5. 以后：改完 → Commit → Push
