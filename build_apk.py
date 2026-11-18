# -*- coding: utf-8 -*-
"""
行测红卷 · 打包 APK
把 web/ 页面、hongjuan.db 题库、题目配图一起塞进一个安卓安装包。

    python build_apk.py            完整构建
    python build_apk.py --assets   只准备资源（图片转换慢，可单独跑）
    python build_apk.py --skip-assets  复用上次准备好的资源，只重编代码

依赖：JDK 17、Android SDK（build-tools 34 + platform android-34）、Pillow。
"""
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ANDROID = os.path.join(HERE, "android")
ASSETS = os.path.join(ANDROID, "assets")
BUILD = os.path.join(ANDROID, "build")
SRC = os.path.join(ANDROID, "src")
RES = os.path.join(ANDROID, "res")
MANIFEST = os.path.join(ANDROID, "AndroidManifest.xml")
WEB = os.path.join(HERE, "web")
DB_SRC = os.path.join(HERE, "hongjuan.db")

SDK = os.environ.get("ANDROID_SDK_ROOT") or r"D:\AI\_android_sdk"
BT = os.path.join(SDK, "build-tools", "34.0.0")
PLATFORM = os.path.join(SDK, "platforms", "android-34", "android.jar")
VAULT_IMG = os.environ.get("HJ_IMG") or r"D:\AI\xingcezhenti\90-图片"

IMAGE_OUT = os.path.join(ASSETS, "img")
PKG = "com.huasufang.hongjuan"
KS = os.path.join(ANDROID, "hongjuan.keystore")
KS_ALIAS = "hongjuan"


def ks_pass():
    """签名密码不写进源码：优先环境变量 HJ_KS_PASS，其次 android/.kspass（不入库）。"""
    p = os.environ.get("HJ_KS_PASS")
    if p:
        return p.strip()
    f = os.path.join(ANDROID, ".kspass")
    if os.path.isfile(f):
        return open(f, encoding="utf-8").read().strip()
    return ""


KSPASS = ks_pass()

sys.stdout.reconfigure(encoding="utf-8")


def run(cmd, cwd=None):
    print("  $", " ".join(cmd[:3]), "..." if len(cmd) > 3 else "")
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        print(p.stdout[-3000:])
        print(p.stderr[-3000:])
        raise SystemExit("命令失败：%s" % cmd[0])
    return p.stdout


# ---------- 1. 资源 ----------

def prepare_www():
    dst = os.path.join(ASSETS, "www")
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(dst, exist_ok=True)
    for name in ("app.js", "style.css"):
        shutil.copy2(os.path.join(WEB, name), os.path.join(dst, name))
    # APK 里没有 /s/ 路由，首页改成相对路径
    html = open(os.path.join(WEB, "index.html"), encoding="utf-8").read()
    html = html.replace("/s/style.css?{{V}}", "style.css").replace("/s/app.js?{{V}}", "app.js")
    open(os.path.join(dst, "index.html"), "w", encoding="utf-8").write(html)
    print("  网页 3 个文件")


def img_references(db_path):
    """题库里所有图片引用，返回 {相对路径: 出现次数}。
    选项存在 JSON 字段里，引号是转义过的，所以两种写法都要认。"""
    con = sqlite3.connect(db_path)
    refs = {}
    pat = re.compile(r'src=\\?"/img/([^"\\]+)')
    for row in con.execute("SELECT stem, analysis, material, options FROM questions"):
        for blob in row:
            if not blob:
                continue
            for m in pat.finditer(blob):
                refs[m.group(1)] = refs.get(m.group(1), 0) + 1
    con.close()
    return refs


def convert_one(rel, out_dir):
    src = os.path.join(VAULT_IMG, rel)
    if not os.path.isfile(src):
        return rel, None
    base = os.path.basename(rel)
    stem, ext = os.path.splitext(base)

    if rel.startswith("题目图/"):
        # 题目图偏大，转 WebP；画质给足，宁可包里大一点
        name = "t_" + stem + ".webp"
        dst = os.path.join(out_dir, name)
        if not os.path.exists(dst):
            try:
                im = Image.open(src)
                im.load()
                if im.mode not in ("RGB", "RGBA"):
                    im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
                im.save(dst, "WEBP", quality=92, method=5)
                if os.path.getsize(dst) >= os.path.getsize(src):
                    os.remove(dst)
                    raise ValueError("bigger")
            except Exception:
                name = "t_" + base
                dst = os.path.join(out_dir, name)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
        return rel, name

    # 公式图原本只有十几像素高，直接显示会被屏幕放大得发虚。
    # 放大 3 倍后压成 4 色 PNG：体积只有无损 WebP 的六分之一，
    # 白底靠 CSS 的 multiply 混色吃掉，页面上看不出来。
    name = "f_" + stem + ".png"
    dst = os.path.join(out_dir, name)
    if not os.path.exists(dst):
        try:
            im = Image.open(src).convert("RGBA")
            big = im.resize((im.width * 3, im.height * 3), Image.LANCZOS)
            flat = Image.new("RGBA", big.size, (255, 255, 255, 255))
            flat.alpha_composite(big)
            flat.convert("L").convert("P", palette=Image.ADAPTIVE, colors=4).save(
                dst, "PNG", optimize=True)
        except Exception:
            # 缩放失败就退回原图，宁可糊也别缺图
            name = "f_" + base
            dst = os.path.join(out_dir, name)
            if not os.path.exists(dst):
                try:
                    os.link(src, dst)
                except OSError:
                    shutil.copy2(src, dst)
    return rel, name


def prepare_images(db_path):
    os.makedirs(IMAGE_OUT, exist_ok=True)
    refs = img_references(db_path)
    if not refs:
        print("  [警告] 题库里没有图片引用")
        return {}
    print("  题库引用图片 %d 张，开始转换…" % len(refs))
    t0 = time.time()
    mapping = {}
    done = [0]

    def work(rel):
        r, name = convert_one(rel, IMAGE_OUT)
        if name:
            mapping[r] = name
        done[0] += 1
        if done[0] % 500 == 0:
            print("    %d / %d" % (done[0], len(refs)), flush=True)

    order = sorted(refs.keys())
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(work, order))
    size = sum(os.path.getsize(os.path.join(IMAGE_OUT, f)) for f in os.listdir(IMAGE_OUT))
    print("  图片 %d 张，%.1f MB，用时 %.0fs"
          % (len(os.listdir(IMAGE_OUT)), size / 1048576, time.time() - t0))
    return mapping


def rewrite_db(mapping):
    """把题库副本里的图片路径改成本地 assets 名字。"""
    dst = os.path.join(ASSETS, "db")
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(dst, exist_ok=True)
    target = os.path.join(dst, "hongjuan.db")
    shutil.copy2(DB_SRC, target)
    if not mapping:
        return target
    con = sqlite3.connect(target)
    # 题干和解析里是 src="/img/…"，选项存在 JSON 里，引号被转义成了 src=\"/img/…
    # 两种形式都要认，否则选项里的公式图会指向不存在的路径。
    # 结尾的引号必须一起吃掉：只替换到引号前再补一个引号，会拼出 src="…"" 这种畸形属性，
    # 部分 WebView 会因此取不到图片。\1 是起始处的转义符（JSON 字段里是 \"，HTML 字段里是 "）。
    pat = re.compile(r'src=(\\?)"/img/([^"\\]+)\\?"')

    def fix(m):
        slash, rel = m.group(1), m.group(2)
        return 'src=' + slash + '"/img/' + mapping.get(rel, rel) + slash + '"'

    rows = con.execute("SELECT qid, stem, analysis, material, options FROM questions").fetchall()
    upd = []
    for qid, stem, ana, mat, opts in rows:
        nstem = pat.sub(fix, stem or "")
        nana = pat.sub(fix, ana or "")
        nmat = pat.sub(fix, mat or "")
        nopts = pat.sub(fix, opts or "")
        if (nstem, nana, nmat, nopts) != (stem or "", ana or "", mat or "", opts or ""):
            upd.append((nstem, nana, nmat, nopts, qid))
    con.executemany(
        "UPDATE questions SET stem=?, analysis=?, material=?, options=? WHERE qid=?", upd)
    # 打包出去的应该是干净的题库，桌面上的做题记录不带走
    for t in ("srs", "reviews", "favorites", "notes", "settings"):
        con.execute("DELETE FROM %s" % t)
    con.commit()
    con.close()
    # 给安卓壳一个版本号：题库变了就重新拷一份并把学习记录迁过去。
    # 只用 mtime+大小，不做内容哈希——打包一次变一次就够了。
    with open(os.path.join(dst, "build.txt"), "w", encoding="utf-8") as fh:
        fh.write("%d-%d" % (int(os.path.getmtime(target)), os.path.getsize(target)))
    print("  题库图片路径改写 %d 行，学习记录已清空" % len(upd))
    return target


# ---------- 2. 编译 ----------

def compile_resources():
    os.makedirs(BUILD, exist_ok=True)
    res_zip = os.path.join(BUILD, "res.zip")
    if os.path.exists(res_zip):
        os.remove(res_zip)
    run([os.path.join(BT, "aapt2.exe"), "compile", "--dir", RES, "-o", res_zip])
    base = os.path.join(BUILD, "base.apk")
    if os.path.exists(base):
        os.remove(base)
    gen = os.path.join(BUILD, "gen")
    os.makedirs(gen, exist_ok=True)
    run([os.path.join(BT, "aapt2.exe"), "link", "-o", base,
         "-I", PLATFORM, "--manifest", MANIFEST,
         "--java", gen, "--min-sdk-version", "21", "--target-sdk-version", "34",
         "--version-code", "1", "--version-name", "1.0", res_zip])
    return base


def compile_java():
    out = os.path.join(BUILD, "classes")
    os.makedirs(out, exist_ok=True)
    sources = []
    for root, _, files in os.walk(SRC):
        for f in files:
            if f.endswith(".java"):
                sources.append(os.path.join(root, f))
    gen = os.path.join(BUILD, "gen")
    for root, _, files in os.walk(gen):
        for f in files:
            if f.endswith(".java"):
                sources.append(os.path.join(root, f))
    run(["javac", "-source", "8", "-target", "8", "-nowarn",
         "-bootclasspath", PLATFORM, "-classpath", PLATFORM,
         "-d", out] + sources)
    return out


def make_dex(classes_dir):
    out = os.path.join(BUILD, "dex")
    os.makedirs(out, exist_ok=True)
    class_files = []
    for root, _, files in os.walk(classes_dir):
        for f in files:
            if f.endswith(".class"):
                class_files.append(os.path.join(root, f))
    if not class_files:
        raise SystemExit("没有编译出 class 文件")
    run([os.path.join(BT, "d8.bat"), "--lib", PLATFORM, "--min-api", "21",
         "--output", out] + class_files)
    dex = os.path.join(out, "classes.dex")
    if not os.path.exists(dex):
        raise SystemExit("d8 没有产出 classes.dex")
    return dex


def assemble(base_apk, dex):
    unsigned = os.path.join(BUILD, "unsigned.apk")
    shutil.copy2(base_apk, unsigned)
    with zipfile.ZipFile(unsigned, "a", zipfile.ZIP_DEFLATED) as z:
        z.write(dex, "classes.dex")
    # 资源分两批：数据库压一压，图片原样存（省打包时间）
    total = 0
    with zipfile.ZipFile(unsigned, "a", zipfile.ZIP_STORED) as z:
        for root, _, files in os.walk(ASSETS):
            for f in files:
                src = os.path.join(root, f)
                arc = "assets/" + os.path.relpath(src, ASSETS).replace(os.sep, "/")
                if arc in z.namelist():
                    continue
                if f.endswith(".db") or f.endswith(".js") or f.endswith(".css") or f.endswith(".html"):
                    z.write(src, arc, zipfile.ZIP_DEFLATED)
                else:
                    z.write(src, arc, zipfile.ZIP_STORED)
                total += os.path.getsize(src)
    print("  assets %.1f MB" % (total / 1048576))
    return unsigned


def sign(unsigned):
    if not KSPASS:
        raise SystemExit(
            "缺少签名密码。二选一：\n"
            "  设置环境变量 HJ_KS_PASS，或把密码写进 android/.kspass（该文件已被 git 忽略）")
    aligned = os.path.join(BUILD, "aligned.apk")
    apk = os.path.join(HERE, "行测红卷.apk")
    if os.path.exists(aligned):
        os.remove(aligned)
    run([os.path.join(BT, "zipalign.exe"), "-f", "4", unsigned, aligned])
    if not os.path.exists(KS):
        run(["keytool", "-genkeypair", "-keystore", KS, "-alias", KS_ALIAS,
             "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
             "-storepass", KSPASS, "-keypass", KSPASS,
             "-dname", "CN=HongJuan, OU=Study, O=Local, L=Local, C=CN"])
    run(["java", "-jar", os.path.join(BT, "lib", "apksigner.jar"), "sign",
         "--ks", KS, "--ks-pass", "pass:" + KSPASS, "--key-pass", "pass:" + KSPASS,
         "--v4-signing-enabled", "false",
         "--out", apk, aligned])
    print("  已签名：%s（%.1f MB）" % (apk, os.path.getsize(apk) / 1048576))
    return apk


def warn_stale_assets():
    """--skip-assets 不重建题库：源库比上次打包新的话，出的包在手机上还是旧题。"""
    bt = os.path.join(ASSETS, "db", "build.txt")
    if not os.path.exists(bt):
        print("  [警告] 缺少 build.txt，安卓端认不出题库版本；建议不做 --skip-assets")
        return
    try:
        built = int(open(bt, encoding="utf-8").read().strip().split("-")[0])
    except Exception:
        print("  [警告] build.txt 读不出来，建议完整构建")
        return
    if os.path.getmtime(DB_SRC) > built:
        print("  [警告] hongjuan.db 比上次打包时更新，这次不会重建题库：")
        print("         手机上仍然用旧库。要更新题库请去掉 --skip-assets。")


def main():
    args = sys.argv[1:]
    t0 = time.time()
    if "--skip-assets" not in args:
        print("[1/5] 准备网页与题库")
        prepare_www()
        db_copy = prepare_images(DB_SRC)
        rewrite_db(db_copy)
    else:
        print("[1/5] 复用已有 assets")
        warn_stale_assets()

    print("[2/5] 编译资源")
    base = compile_resources()
    print("[3/5] 编译 Java")
    classes = compile_java()
    print("[4/5] 生成 dex")
    dex = make_dex(classes)
    print("[5/5] 打包与签名")
    unsigned = assemble(base, dex)
    apk = sign(unsigned)
    print("完成，用时 %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
