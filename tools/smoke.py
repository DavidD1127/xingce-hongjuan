# -*- coding: utf-8 -*-
"""
行测红卷 · 真机冒烟

一条命令跑完：装包（可选）→ 启动 → 抽题 → 截图 → 统计资源缺失。

    python tools/smoke.py                 # 用已装的那版跑一遍
    python tools/smoke.py --install       # 先装上当前目录的 apk
    python tools/smoke.py --serial XXX    # 指定设备（多台时）

坐标按 1080×2376 设计，脚本会按真实分辨率等比换算；
换机型后如果点不中，改 BASE_W / BASE_H 附近的那组比例即可。
"""
import argparse
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APK = os.path.join(HERE, "行测红卷.apk")
PKG = "com.huasufang.hongjuan"
ACT = PKG + "/.MainActivity"
SHOTS = os.path.join(HERE, ".share", "shots")

ADB = os.environ.get("HJ_ADB") or r"D:\Program Files\Netease\MuMu Player 12\nx_main\adb.exe"

BASE_W, BASE_H = 1080.0, 2376.0            # 设计基准
PT_TAB_STUDY = (270, 2255)                 # 底部「练习」
PT_ALL_MODULE = (205, 500)                 # 「全部模块」
PT_START = (240, 1930)                     # 「开始抽题」
PT_SKIP = (287, 1658)                      # 题目页「跳过」


def sh(args, timeout=120):
    p = subprocess.run(args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, (p.stdout or ""), (p.stderr or "")


def adb(serial, *args, timeout=120):
    return sh([ADB, "-s", serial] + list(args), timeout=timeout)


def pick_device(want):
    rc, out, err = sh([ADB, "devices"])
    if rc != 0:
        sys.exit("adb 调不动：%s" % err.strip())
    devs = [l.split()[0] for l in out.splitlines()[1:] if l.strip().endswith("device")]
    if not devs:
        sys.exit("没有已授权的设备，先插线并允许 USB 调试")
    if want:
        if want not in devs:
            sys.exit("设备 %s 不在列表：%s" % (want, ", ".join(devs)))
        return want
    if len(devs) > 1:
        print("  多台设备，用第一台 %s（可用 --serial 指定）" % devs[0])
    return devs[0]


def screen_size(serial):
    rc, out, _ = adb(serial, "shell", "wm", "size")
    m = re.search(r"(\d+)x(\d+)", out)
    if not m:
        return int(BASE_W), int(BASE_H)
    return int(m.group(1)), int(m.group(2))


def pt(serial, xy, w, h):
    x = int(round(xy[0] / BASE_W * w))
    y = int(round(xy[1] / BASE_H * h))
    adb(serial, "shell", "input", "tap", str(x), str(y))


def shot(serial, name):
    os.makedirs(SHOTS, exist_ok=True)
    path = os.path.join(SHOTS, name)
    with open(path, "wb") as f:
        p = subprocess.run([ADB, "-s", serial, "exec-out", "screencap", "-p"],
                           stdout=f, timeout=60)
    return path if p.returncode == 0 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true", help="先安装当前 apk")
    ap.add_argument("--serial", default="", help="指定设备序列号")
    ap.add_argument("--drill", type=int, default=6, help="抽题后连跳几次找带图题")
    args = ap.parse_args()

    if not os.path.isfile(ADB):
        sys.exit("找不到 adb：%s（可用环境变量 HJ_ADB 指定）" % ADB)

    serial = pick_device(args.serial)
    w, h = screen_size(serial)
    print("设备 %s，分辨率 %dx%d" % (serial, w, h))

    if args.install:
        if not os.path.isfile(APK):
            sys.exit("没找到 apk：%s" % APK)
        print("安装 %s（%d MB，等一会）…" % (os.path.basename(APK), os.path.getsize(APK) // 1048576))
        rc, out, err = adb(serial, "install", "-r", "-d", APK, timeout=900)
        if "Success" not in out:
            sys.exit("安装失败：%s" % (out + err).strip()[-400:])
        print("  装好了")

    adb(serial, "logcat", "-c")
    adb(serial, "shell", "am", "force-stop", PKG)

    t0 = time.time()
    rc, out, err = adb(serial, "shell", "am", "start", "-W", "-n", ACT, timeout=120)
    cost = int((time.time() - t0) * 1000)
    if "Status: ok" not in out:
        print("启动失败：")
        print((out + err).strip()[-600:])
        sys.exit(1)
    m = re.search(r"TotalTime:\s*(\d+)", out)
    print("启动成功，耗时 %sms%s" % (m.group(1) if m else "?", ""))

    time.sleep(4)
    p1 = shot(serial, "smoke-home.png")
    print("  首页截图 %s" % p1)

    # 抽一轮题再看页面
    pt(serial, PT_TAB_STUDY, w, h)
    time.sleep(1.5)
    pt(serial, PT_ALL_MODULE, w, h)
    time.sleep(1.0)
    adb(serial, "shell", "input", "swipe", str(int(w * 0.5)), str(int(h * 0.76)),
        str(int(w * 0.5)), str(int(h * 0.38)), "250")
    time.sleep(1.0)
    pt(serial, PT_START, w, h)
    time.sleep(3.5)
    p2 = shot(serial, "smoke-question.png")
    print("  答题页截图 %s" % p2)

    for i in range(max(0, args.drill)):
        pt(serial, PT_SKIP, w, h)
        time.sleep(1.2)
    if args.drill:
        p3 = shot(serial, "smoke-after-skip.png")
        print("  跳题后截图 %s" % p3)

    rc, log, _ = adb(serial, "logcat", "-d", "-s", "HJ")
    miss = [l for l in log.splitlines() if "asset-miss" in l]
    real = [l for l in miss if "favicon.ico" not in l]
    img_miss = [l for l in real if "/img/" in l]

    print()
    print("=" * 46)
    print("资源缺失 %d 条（其中图片 %d 条）" % (len(real), len(img_miss)))
    for l in real[:8]:
        print("  " + l.split("HJ", 1)[-1].strip()[:120])
    if len(real) > 8:
        print("  …还有 %d 条" % (len(real) - 8))
    print("=" * 46)
    print("结论：%s" % ("通过（无缺失）" if not real else "有缺失，见上"))
    return 0 if not real else 2


if __name__ == "__main__":
    sys.exit(main())
