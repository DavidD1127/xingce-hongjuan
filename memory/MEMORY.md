# MEMORY

行测红卷项目（工作区 `D:\ds\apk`）的长期索引。细节看 `HANDOFF.md` 和按日期的记录。

## 项目是什么

把上游行测真题（`D:\AI\xingcezhenti`）做成可离线刷题的 APK，桌面网页版做调试壳。
去重后 27,473 题，六科；SM-2 间隔复习；红白作业本风格 UI。

## 技术底

- 桌面：`server.py`（标准库 http.server + sqlite3），端口 8400，前端 `web/` 原生 JS
- 安卓：`android/` 手写 Java + WebView，题库 SQLite 打进 assets，页面走 `https://app.local/` 拦截器
- 打包：`build_apk.py`（aapt2 → javac → d8 → zip → zipalign → apksigner），无 Gradle
- 环境：JDK 17、Python 3.12、Android SDK 34（`D:\AI\_android_sdk`）、Pillow、MuMu 模拟器

## 当前状态（2026-11-18）

- 桌面版可用，`启动.bat` 双击即跑（可见窗口，关窗即停）
- APK 156MB；题库更新走 `build.txt` 版本比对 + 学习记录迁移
- 选项公式图已修（路径改写与题库同步两个 bug）
- 新增：进度导出/导入、长材料展开、缺图占位、`tools/smoke.py` 真机冒烟
- 待真机验证本轮改动（设备当天未连接）
- git 已初始化，提交到「搬到新工作区，二维码指向 zip 下载」

## 硬约束 / 偏好

- UI 不要 AI 味：红白两色、直角、宋体、无渐变圆角 emoji
- 用户对体积不敏感，但别离谱（435MB 被打回，156MB 接受）
- 手机是一加 PKR110 / Android 16，装自制应用会被拦（下载 + 未知来源 + 纯净模式三处）
- 用户要「能自己把服务拉起来」，别搞隐藏后台进程

## 坑

公式图源图只有 15×33，放大 3 倍压 4 色 PNG 才既清楚又不撑包；
选项图片在 JSON 里路径是转义的，打包扫描要兼容；`file://` 互读在 API 30+ 被禁。
