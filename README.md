# PerfMTK-Manager 中文版自动构建

上游 `JUANIMAN/PerfMTK-Manager` 只有英语和西班牙语，且是 Flutter AOT 编译（文案烧在
`libapp.so` 里），**无法通过替换资源文件汉化**。本仓库用 GitHub Actions 每天检查上游更新，
自动重新打一遍中文补丁并编译出 APK 发布。

## 为什么用脚本而不是 git patch / fork 合并

上游几乎每次发版都会往 `lib/localization/app_locales.dart` 里加新字符串。任何存档的 diff
都会**每次都冲突**。所以这里的做法是：

```
克隆上游该次提交 → tools/apply_zh.py 重新生成 zh map → 编译
```

- 译文存在 `tools/zh_strings.json`（300 条），与行号无关，上游重构本地化文件也不会失效。
- 上游新增的键**不会导致构建失败**：脚本用英文原文兜底，并在日志 / Release 说明里列出
  "这次新增了哪些还没翻译的键"，你随时补进去即可。
- 本仓库**不含任何上游源码**，所以永远不会出现合并冲突。

## 一次性配置（约 5 分钟）

### 1. 建仓库

在 GitHub 新建一个**空仓库**（public 或 private 都行；private 每月 2000 分钟免费额度，
本工作流单次约 6–8 分钟，绰绰有余）。

把本目录推上去：

```bash
git init
git add .
git commit -m "chore: bootstrap Chinese auto-build"
git branch -M main
git remote add origin git@github.com:<你的用户名>/perfmtk-cn.git
git push -u origin main
```

目录结构应为：

```
.github/workflows/build-zh.yml
tools/apply_zh.py
tools/zh_strings.json
README.md
```

### 2. 添加 4 个 Secrets

仓库 → Settings → Secrets and variables → Actions → New repository secret：

| Name | Value |
|---|---|
| `KEYSTORE_BASE64` | `keystore.b64.txt` 里的整行内容（已为你生成） |
| `KEYSTORE_PASSWORD` | 见本地 `SETUP-SECRETS.local.md` |
| `KEY_ALIAS` | `perfmtk` |
| `KEY_PASSWORD` | 见本地 `SETUP-SECRETS.local.md` |

> **为什么用这个密钥**：你手机上现在装的汉化版就是用 `D:\pmbuild\pm-release.jks`
> 签名的。CI 必须用**同一个**密钥签名，否则以后每个新版本都要先卸载再装。
> 这个密钥是一次性生成的个人自用密钥，请自己留一份备份
> （`D:\pmbuild\pm-release.jks`），丢了就只能卸载重装。

### 3. 开启 Actions

仓库 → Actions 标签页 → 允许工作流运行。之后：

- **每天 11:00（北京时间）自动跑一次**；
- 也可以在 Actions → Build Chinese APK → Run workflow 手动触发，
  勾选 `force` 可以强制重建当前版本。

产物会出现在仓库的 **Releases** 页，文件名形如
`PerfMTK-Manager-zh-8.9.0-bee54da.apk`。

## 装到手机上

### 方式一：手动

每次到 Releases 下载最新 APK 覆盖安装即可（签名一致，**不需要卸载**）。

### 方式二：自动更新（推荐）

用 [Obtainium](https://github.com/ImranR98/Obtainium)：

1. 添加应用 → 填你的仓库地址 `https://github.com/<你>/perfmtk-cn`
2. 它会监听该仓库的 Releases，上游一更新、CI 出包后自动提示/自动安装

## 日常维护

### 补新出现的译文

上游加新键后，看那次 CI 的日志或 Release 说明，会看到类似：

```
[note] 3 new untranslated key(s) currently show English:
       someNewKey, anotherKey, thirdKey
```

在 `tools/zh_strings.json` 里按同样格式加进去就行：

```json
{
  "someNewKey": "你的中文翻译",
  ...
}
```

（文件是按 key 排序的 JSON，值是**纯文本**，不要带 Dart 的引号和转义。）
提交后下次运行就会用上。

### 从现有构建里重新导出译文

如果你在别处改过中文，可以反向导出：

```bash
python3 tools/apply_zh.py <已汉化的源码目录> --extract
```

### 只检查不修改

```bash
python3 tools/apply_zh.py <源码目录> --check-only
```

## 失败排查

| 现象 | 原因 / 处理 |
|---|---|
| `Dart compile error`，报某个新 API 不存在 | 上游用了比 runner 上更新的 Flutter。把 `build-zh.yml` 里的 `FLUTTER_CHANNEL: stable` 保留（默认拉最新），或反过来把 `subosito/flutter-action` 换成 `flutter-version: '<已知可用版本>'` |
| `Failed to install SDK components` | runner 的 Android SDK 缺组件，AGP 会自动下载；偶发网络问题重跑一次即可 |
| `keystoreProperties.getProperty("storeFile") must not be null` | 4 个 Secrets 没配全，或 `android/local.properties` 被清掉了 |
| 构建成功但界面还是英文 | 看那次日志里 `apply_zh.py` 的 4 行 "registered / added" 是否都在；缺哪条说明上游把那个锚点改了，需要更新 `apply_zh.py` 里的正则 |
| 安装报 `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | 签名和已安装版本不一致（换了密钥）。只能卸载一次再装 |

## 上游更新后需要人工介入的两种情况

1. **本地化文件结构大改**（比如换成 ARB / gen-l10n）：`apply_zh.py` 找不到 `en` map 会
   直接 `[FAIL]` 退出，CI 报错。这时需要按新结构改脚本（译文 JSON 可以复用）。
2. **新增了需要翻译的 Dart 字符串不在 map 里**（硬编码在 UI 代码中）：脚本只能处理 map
   里的键。这种情况需要单独打补丁。

除此之外，日常更新是全自动的。

## 许可

上游为 MIT。本仓库仅包含构建脚本与译文，同样以 MIT 发布。译文基于上游界面文案翻译，
如上游作者愿意收录，可直接把 `tools/zh_strings.json` 转成他的 map 格式提交 PR。
