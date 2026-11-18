# 行测红卷

行测真题的间隔复习工具。题库、进度都在一个 SQLite 文件里，不联网，装个 Python 就能跑。

- 桌面版：Python 3.8+，标准库，无第三方依赖。Windows 有 `启动.bat`，macOS / Linux 直接 `python server.py`
- 手机版：额外要 JDK 17、Android SDK 34、Pillow，出的是离线 APK（题库和配图全在包里）

题源：`D:\AI\xingcezhenti`（ERRRC/xingcezhenti 的原始题库副本，515 套卷、58,890 行题目）。
按 qid 去重后 **27,473 道**，六科：政治理论、常识判断、言语理解、数量关系、判断推理、资料分析。

## 题库从哪来

题库是别人整理的 Obsidian vault，不在本仓库里（一是体积，二是版权在人家的）。
目录长这样，`build_db.py` 按这个结构找题：

```
01-政治理论/  *.md
02-常识判断/
03-言语理解与表达/
04-数量关系/
05-判断推理/
06-资料分析/
90-图片/      配图，路径由 HJ_IMG 指定
```

每篇 Markdown 里用 `### 第 N 题 <sub>qid 123 · 考点</sub>` 分题，
选项写成 `- **A**. 内容`，答案写成 `**答案**：A`，后面跟解析。
想完全对上格式，直接看 `sample/` 里那六篇——就是按解析规则写的。

## 跑起来

**手上还没有题库也能先看效果**。仓库里带了一份 12 道题的示例（六个科目各两题），
导入后就能把界面完整跑一遍：

```
python build_db.py sample --out sample.db     # 从 sample/ 导入示例题
set HJ_DB=sample.db                            # PowerShell: $env:HJ_DB="sample.db"
python server.py
```

换成自己的题库就去掉 `HJ_DB`，用默认的 `hongjuan.db`。

正式用法：

双击 `启动.bat`（会自己开浏览器）。
命令行也行：

```
python build_db.py    # 第一次，或者题库有更新时跑一次，约 3 秒
python server.py      # 起服务，默认 8400
```

地址 <http://127.0.0.1:8400>。

`build_db.py` 需要一个特定结构的 Obsidian 题库目录（六个科目子目录，每篇 Markdown 记
若干道题），见下面的「题库从哪来」。没有的话只能跑示例。

## 有什么

- **练习**：选科目、选地区（34 个）、选题量，随机抽新题。答完看解析，再自评记得多少。中途想换科目或换地区，点「换范围」或导航上的「练习」就能退回，已作答的记录不受影响。
- **复习**：SM-2 到期的题自动排进队列，没到期的不会来烦你。
- **错题**：答错的自动进来，可以只练错题。
- **题库**：按模块、考点、年份、地区、关键词查，点进去看解析。
- **统计**：三十天做题量、各科进度、错得最多的考点。

自评四档对应 SM-2 的 1/3/4/5：忘了、勉强、一般、熟了。忘了就明天再见，熟了间隔翻倍往上走。

键盘也能用：`A`–`D` 选，`Enter` 对答案，`1`–`4` 自评。

## 启动与停止

和原项目一个路子：双击 `启动.bat`，出来一个黑色窗口，服务就跑在那个窗口里。

- 窗口留着 = 服务在跑，关掉窗口 = 服务停止
- 窗口里如果自己退出了，会在 3 秒后重新拉起来，日志直接打在窗口里，看得到发生了什么
- 想确认活着：`netstat -ano | findstr :8400`，出现 `LISTENING` 就是活着
- 开机不会自启，重启电脑后需要再双击一次

## 文件

```
build_db.py    题库 Markdown → hongjuan.db
server.py      后端，标准库，无依赖
web/           前端三个文件，原生 JS
android/       安卓壳工程（WebView + 本地 SQLite）
build_apk.py   打包 APK
tools/smoke.py 真机冒烟：装包 → 启动 → 抽题 → 截图 → 统计资源缺失
hongjuan.db    题库 + 进度（约 85MB，跑 build_db.py 生成）
```

`hongjuan.db` 是全部数据。备份就是拷这一个文件。删了重跑 `build_db.py` 也没事，就是进度清空。

## 环境变量

有些路径跟机器绑定，都用环境变量覆盖，不写死在代码里：

| 变量 | 作用 | 默认值 |
| --- | --- | --- |
| `HJ_IMG` | 上游图片目录（`90-图片`） | `D:\AI\xingcezhenti\90-图片` |
| `ANDROID_SDK_ROOT` | Android SDK 位置 | `D:\AI\_android_sdk` |
| `HJ_KS_PASS` | 签名密码；也可写进 `android/.kspass`（不入库） | 无，缺失会直接报错 |
| `HJ_ADB` | adb 路径，冒烟脚本用 | MuMu 自带的那份 |
| `HJ_DB` | 桌面版读哪个库 | `./hongjuan.db` |
| `HJ_PORT` | 桌面版端口 | `8400` |

换机器只要把这几个指对，代码不用改。

## 手机版（APK）

```
python build_apk.py
```

跑完根目录多一个 `行测红卷.apk`（约 156MB）。装到手机上就是离线版：题库、配图全在包里，做题记录存本机，不联网。

首次打开会把题库从安装包解到应用目录，等几秒就好。之后启动是秒开。

**题库会随版本更新**：打包时写一份 `assets/db/build.txt`，应用启动时和库里的版本号对比，
不一致就备份旧库、拷新库，再把 `srs / reviews / favorites / notes` 四张表迁过去。
所以覆盖安装不会丢做题记录。

做题记录可以手动导出：今日页底部「进度保险」→ 导出走系统分享面板，换机后在同一个地方粘贴导入。

竖屏锁定，导航在屏幕底部，按钮都按拇指大小做的。

构建需要三样东西：JDK 17、Android SDK（build-tools 34 + platform android-34）、Pillow。三样都到位才能出包，缺一样会直接报错退出。

和桌面版的关系：两边数据不互通。桌面版改动做在 `web/`，APK 用的就是同一套页面，只是把 `fetch('/api/…')` 换成 `HJNative.call(…)` 走本地库。

## 改哪里

| 想改 | 去哪 |
| --- | --- |
| 配色、字体、间距 | `web/style.css` 开头那组 `--red` `--paper` 变量 |
| 首页文案、按钮 | `web/app.js` 的 `viewHome` |
| 出题规则、间隔算法 | `server.py` 的 `pick()` 和 `schedule()` |
| 题面字段 | `build_db.py` 的 `build_question()` |

图片不复制，直接读上游目录。换题库时把 `HJ_IMG` 环境变量指到新的 `90-图片` 就行。

## 发版

Android 只认 `versionCode` 判断升级，所以版本号跟着包走：

```
python build_apk.py --bump        # 版本号 +1 再出包，versionName 变成 1.0.N
python tools/smoke.py --install   # 真机过一遍
git tag v1.0.N && git push origin main --tags
gh release create v1.0.N 行测红卷.apk --notes-file docs/release-notes.md
```

细节见 [`docs/发版.md`](docs/发版.md)，Release 正文模板在 [`docs/release-notes.md`](docs/release-notes.md)。

签名 keystore 一丢就再也无法覆盖安装，务必另外备份。

## 和原项目的差别

砍掉了这些：多账号注册登录、模拟考试、疑点复核、考点导航、运营面板、Service Worker、云同步。

留下的核心是「抽题 → 判分 → 自评 → 按记忆曲线回来」。代码从 1700 + 1600 行降到 420 + 700 行，去掉的东西都能在 git 历史里找回来。

## 已知情况

- 111 道判断题原文没有选项，导入时补成「A 正确 / B 错误」。
- 4 道题原文缺答案，不进练习队列。
- 少数题干里有残留的 Markdown 加粗，前端渲染时会转成 `<b>`。
- 图片加载失败会显示虚线「图缺失」占位，不再留空白——这样能分清是缺图还是渲染坏了；
  失败路径同时记在 `window.MISSING_IMG` 和 logcat 的 `img-miss` 里，方便补素材。
- 题库里 39,463 条图片引用中，上游缺 2 张（都在解析里），其余齐全。

题库版权归原出题方与整理者，这套工具只给自己看书用。

## 没有进仓库的东西

| 内容 | 原因 |
| --- | --- |
| `hongjuan.db` | 85MB，能由 `build_db.py` 重建 |
| `android/assets/` | 打包时从题库和图片复制生成，约 215MB |
| `*.apk` `*.keystore` `*.idsig` | 产物与签名材料 |
| `android/.kspass` | 本机签名密码 |
| `memory/` | 个人工作记录，含本机路径与偏好 |
| `.share/` | 临时局域网分发目录 |

克隆下来后 `python build_db.py` 重建题库、`python build_apk.py` 出包即可；
首次打包会自动生成一个测试用 keystore，正式分发前记得换成自己的并备份好——
换了签名就只能卸载重装。
