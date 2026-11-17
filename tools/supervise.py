# -*- coding: utf-8 -*-
"""
守着 server.py 的看门程序：服务挂了 2 秒内重新拉起来。

由启动文件夹里的 start-hidden.vbs 在登录时无窗口启动，
日志写到 tools/server.log，出问题先看这个文件。
"""
import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(HERE, "server.py")
LOG = os.path.join(HERE, "tools", "server.log")


def port_busy(port=8400):
    s = socket.socket()
    s.settimeout(0.5)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def note(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except OSError:
        pass


if port_busy():
    note("8400 已被占用，看门程序退出（可能已经在跑）")
    sys.exit(0)

note("看门程序启动")

while True:
    f = None
    try:
        f = open(LOG, "a", encoding="utf-8")
        kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        p = subprocess.Popen([sys.executable, SERVER], cwd=HERE,
                             stdout=f, stderr=subprocess.STDOUT, **kw)
        note("server.py 启动，pid=%d" % p.pid)
        p.wait()
        note("server.py 退出，code=%s" % p.returncode)
    except Exception as e:
        note("启动失败：%s" % e)
    finally:
        if f:
            f.close()
    time.sleep(2)
