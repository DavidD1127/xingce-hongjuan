# 行测红卷 · 开发笔记

做这个项目时踩过的坑、定下来的规矩、还没做完的事。改代码前扫一眼，能少走很多弯路。

## 一句话

把 27,473 道行测真题做成能刷能复习的工具，最终交付物是 APK；桌面网页版是同源代码的调试壳。

## 目录

```
build_db.py    上游 Markdown → hongjuan.db（去重后 27,473 题）
server.py      桌面版后端，标准库，端口 8400
web/           前端三件套，原生 JS，桌面和 APK 共用
android/       安卓壳：Java + WebView + 本地 SQLite
build_apk.py   打包 APK
tools/smoke.py 真机冒烟：装包→启动→抽题→截图→统计资源缺失
sample/        12 道示例题，克隆后能直接跑起来
```

题库（`hongjuan.db`）、图片资源（`android/assets/`）、安装包都在 .gitignore 里，
由脚本重新生成。

## 现在的状态

- 桌面：双击 `启动.bat`，窗口可见，关窗即停；窗口内异常退出 3 秒后自动重启
- APK：真机（一加 PKR110 / Android 16）跑过完整流程——抽题、判分、自评、统计、复习、错题
- 题库更新会带着学习记录一起迁移，覆盖安装不丢进度
- 学习记录可导出/导入（今日页底部「进度保险」）

## 定下来的规矩

1. **作业本风格**：红白两色、直角、宋体标题，不用渐变、圆角、emoji。
2. **SM-2 + 四档自评**：忘了 / 勉强 / 一般 / 熟了，对应 1/3/4/5。
   判分只决定对错，自评才决定下次什么时候回来。
3. **qid 是稳定键**：进度表用题库自带题号，不用自增 id，重导入不丢。
4. **APK 不是套壳网站**：题库 SQLite 在包里，Java 直接查，页面走 `HJNative.call()` 桥，断网可用。
5. **图片策略**：题目图 WebP q92；公式图放大 3 倍压成 4 色 PNG，白底靠 CSS `multiply` 吃掉。
6. **题库随版本走**：打包时写 `assets/db/build.txt`，应用启动时和库里的版本号比对，
   不同就备份旧库 → 拷新库 → ATTACH 迁移 `srs / reviews / favorites / notes`。
   **别退回「有库就跳过」的老逻辑**——那会让用户永远用第一版题库，图片改名后全部 404。

## 踩过的坑

- **`file://` 页读不了 `file://` 资源**（API 30+）：页面和图片统一走 `https://app.local/`，
  由 `shouldInterceptRequest` 从 assets 取。
- **选项只含图片时被当成空**：`optHtml` 去标签后是空字符串，会吞掉整个选项。判断要先看有没有 `<img>`。
- **打包扫图片漏了 options 字段**：选项存在 JSON 里，引号转义成 `src=\"…\"`，正则必须兼容两种写法。
- **静态资源强缓存 1 小时**：改完前端浏览器还在用旧的。已改成 `no-cache` + 首页注入 mtime 版本号。
- **bat 必须 CRLF + 纯 ASCII**：中文 + LF 换行会让 cmd 解析崩掉，报一堆 `is not recognized`。
- **服务不能挂在后台任务里**：任务结束进程会被收走。用可见的 `启动.bat`，双击跑、关窗停。
- **公式图源分辨率只有 15×33**：直接用会糊。放大 3 倍再显示；无损 WebP 会把包撑到 435MB，4 色 PNG 只要 65MB。
- **改写图片路径把结尾引号一起吃掉**：正则少了 `\\?"`，会拼出 `src="/img/x.png""`。
- **改题库必须能进设备**：`ensure()` 只看「库存在与否」，新包换了图名也照旧读老库，
  症状是「题干图正常、选项图全空」。
- **真机调试用 logcat 看资源命中**：把 `MainActivity.LOG_ASSETS` 打开后
  `adb logcat -s HJ` 能看到每条 `asset-ok / asset-miss`，比猜快得多。排查完记得关。
- **材料会挂到不该挂的题上**：一份材料本该只配紧跟着的 4-5 道题，但有些卷子只写了「材料 2」，
  后面几十道普通题也算在它名下。现在设了上限 8 题/组，超出就断。
  **别改成「按材料正文里的『回答下列N题』取数量」**——试过，全库只有 6 组材料写了这句话，
  改完 1040 组全剩 1 题，真正需要材料的题反而丢了材料，比错挂更糟。
  另外材料组的键要带文件名：同一份卷子拆成多篇笔记时，各自都有「材料 2」。

## 还没做

- [ ] 少数题选项图仍空白：现在会显示「图缺失」占位，能分清是数据缺图和渲染坏了。
      定位看 `window.MISSING_IMG` 或 logcat 的 `img-miss`。
- [ ] 换机安装被系统拦（一加/OPPO 纯净模式）：说明写在 release notes 里，够用。

## 常用命令

```
python build_db.py                  # 重建题库，约 3 秒
python build_apk.py                 # 出包，6-8 分钟
python build_apk.py --bump          # 版本号 +1 再出包（发版用）
python build_apk.py --skip-assets   # 只改代码时复用资源（题库变了别用，脚本会警告）
python server.py                    # 桌面版，8400
python tools/smoke.py --install     # 真机冒烟：装包+启动+抽题+截图+缺失统计
```

真机调试：

```
adb -s <serial> install -r 行测红卷.apk
adb -s <serial> shell pm clear com.huasufang.hongjuan     # 清学习记录
adb -s <serial> shell am start -n com.huasufang.hongjuan/.MainActivity
# WebView 调试已开：setWebContentsDebuggingEnabled
adb forward tcp:9230 localabstract:webview_devtools_remote_<pid>
curl http://127.0.0.1:9230/json/list
```

## 环境

JDK 17、Python 3.12、Android SDK 34（build-tools 34.0.0 + platform android-34）、Pillow。

路径都能用环境变量覆盖，见 README 的「环境变量」一节；签名密码走 `HJ_KS_PASS`
或 `android/.kspass`，别写回代码里。
