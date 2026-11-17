# 行测红卷 · 交接单

> 给下一个会话（或未来的自己）看的。读完这份，能直接接着干，不用重新摸一遍。
> 最后更新：2026-11-17 17:30

## 一句话

把 27,473 道行测真题做成一个能刷、能复习的工具，**最终交付物是一个 APK**；桌面网页版是同源代码的调试壳。

## 在哪

- 项目根：`D:\ds\apk`（DSH 工作区，2026-11-17 从 `D:\AI\xingce-hongjuan` 搬来）
- 题库上游：`D:\AI\xingcezhenti`（Obsidian vault，2,962 篇 md、39,461 张图，别改它）
- Android SDK：`D:\AI\_android_sdk`（build-tools 34.0.0 + platforms/android-34）
- 模拟器：MuMu Player 12，`D:\Program Files\Netease\MuMu Player 12`，adb 在其中 `nx_main\adb.exe`

## 组成

```
build_db.py    上游 md → hongjuan.db（去重后 27,473 题）
server.py      桌面版后端，标准库，端口 8400
web/           前端（原生 JS，三件套），桌面和 APK 共用
android/       安卓壳：Java + WebView + 本地 SQLite（手工 aapt2 构建，无 Gradle）
build_apk.py   打包 APK
hongjuan.db    题库 + 学习记录（85MB，gitignore，可重建）
行测红卷.apk   产物（156MB）
.share/        局域网分发目录（gitignore）
```

## 现在能做什么

- 桌面：双击 `启动.bat`，窗口可见，关窗即停；窗口内异常退出会 3 秒后自动重启
- APK：模拟器验证通过（抽题、图片、判分、导航、公式图）；真机装过一版，公式图问题已在最新包里修复
- 数据：`hongjuan.db` 单文件，桌面与手机各自一份，互不相通

## 关键决策（别推翻）

1. **作业本风格 UI**：红白两色、直角、宋体标题，不搞渐变/圆角/emoji。用户明确要「不要 AI 味」。
2. **SM-2 + 四档自评**：忘了/勉强/一般/熟了，对应 1/3/4/5。判分和记忆分开，自评才决定下次到期。
3. **qid 是稳定键**：进度表用题库自带题号，不用自增 id，重导入不丢。
4. **APK 不是套壳网站**：题库 SQLite 在包里，Java 直接查，页面走 `HJNative.call()` 桥；断网可用。
5. **图片策略**：题目图 WebP q92；公式图放大 3 倍压成 4 色 PNG（白底靠 CSS `multiply` 吃掉）。见「踩过的坑」。

## 踩过的坑（别再犯）

- **`file://` 页读不了 `file://` 资源**（API 30+）：页面和图片统一走 `https://app.local/`，`shouldInterceptRequest` 从 assets 取。
- **选项只含图片时被当成空**：`optHtml` 去标签后是空字符串，会吞掉整个选项。判断要先看有没有 `<img>`。
- **打包扫图片漏了 options 字段**：选项存在 JSON 里，引号转义成 `src=\"…\"`，正则必须兼容两种写法。
- **静态资源强缓存 1 小时**：改完前端浏览器还在用旧的。已改成 `no-cache` + 首页注入 mtime 版本号。
- **bat 必须 CRLF + 纯 ASCII**：中文 + LF 换行会让 cmd 解析崩掉，报一堆 `is not recognized`。
- **服务不能挂在会话进程树里**：DSH 后台任务结束后进程会被收走。用可见的 `启动.bat`（用户自己双击）最稳。
- **公式图源分辨率只有 15×33**：直接用会糊。放大 3 倍再显示；无损 WebP 会把包撑到 435MB，4 色 PNG 只要 65MB。

## 待办

- [ ] 真机完整回归（用户手机是一加 PKR110 / Android 16）：装包、抽题、图片、判分
- [ ] 用户手机上安装被拦的问题：已给方案（改名 zip 下载 + 允许未知来源 + 关纯净模式），待确认落地
- [ ] 资料分析长材料在小屏上的阅读体验（现在限高 38vh 滚动）
- [ ] 是否要做进度导入导出（换机不丢）
- [ ] `.apk` 与 `.zip` 双份分发目录 `.share/`，下载完记得关 8088 服务

## 常用命令

```
python build_db.py            # 重建题库（3 秒）
python build_apk.py           # 出包（6-8 分钟，图片全量重转时更久）
python build_apk.py --skip-assets   # 只改代码时复用资源
python server.py              # 桌面版，8400
```

模拟器调试：

```
adb connect 127.0.0.1:16384
adb -s 127.0.0.1:16384 install -r 行测红卷.apk
adb -s 127.0.0.1:16384 shell pm clear com.huasufang.hongjuan
adb -s 127.0.0.1:16384 shell am start -n com.huasufang.hongjuan/.MainActivity
# WebView 调试：MainActivity 里已开 setWebContentsDebuggingEnabled
adb forward tcp:9230 localabstract:webview_devtools_remote_<pid>
curl http://127.0.0.1:9230/json/list
```

## 环境依赖

JDK 17、Python 3.12（`C:\Users\35429\AppData\Local\Programs\Python\Python312`）、Android SDK 34、Pillow。
图片源目录可用 `HJ_IMG` 覆盖，端口可用 `HJ_PORT`。
