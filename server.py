# -*- coding: utf-8 -*-
"""
行测红卷 · 后端
标准库单文件：http.server + sqlite3，无第三方依赖。
数据：hongjuan.db（只这一份，题库与进度都在里面）
配图：直接读上游题库的 90-图片 目录，不复制。
"""
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.parse
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "hongjuan.db")
WEB = os.path.join(HERE, "web")
IMG = os.environ.get("HJ_IMG") or r"D:\AI\xingcezhenti\90-图片"
PORT = int(os.environ.get("HJ_PORT") or 8400)

_lock = threading.Lock()


def conn():
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def today():
    return date.today().isoformat()


def one(sql, args=()):
    c = conn()
    try:
        r = c.execute(sql, args).fetchone()
        return dict(r) if r else None
    finally:
        c.close()


def many(sql, args=()):
    c = conn()
    try:
        return [dict(r) for r in c.execute(sql, args).fetchall()]
    finally:
        c.close()


def write(sql, args=()):
    c = conn()
    try:
        with _lock:
            c.execute(sql, args)
            c.commit()
    finally:
        c.close()


# ---------- 进度导出 / 导入 ----------

def export_progress():
    return {
        "app": "hongjuan",
        "version": 1,
        "exported": today(),
        "srs": many("SELECT qid,status,ease,interval,reps,lapses,due,last,right_cnt,wrong_cnt FROM srs"),
        "reviews": many("SELECT qid,grade,right,ts FROM reviews"),
        "favorites": many("SELECT qid,added FROM favorites"),
        "notes": many("SELECT qid,text,updated FROM notes"),
    }


def import_progress(body):
    srs = body.get("srs") or []
    rev = body.get("reviews") or []
    fav = body.get("favorites") or []
    nts = body.get("notes") or []
    if not any([srs, rev, fav, nts]):
        return {"error": "这份 JSON 里没有可导入的记录"}
    c = conn()
    try:
        with _lock:
            c.execute("DELETE FROM srs")
            c.execute("DELETE FROM reviews")
            c.execute("DELETE FROM favorites")
            c.execute("DELETE FROM notes")
            c.executemany(
                "INSERT OR REPLACE INTO srs(qid,status,ease,interval,reps,lapses,due,last,right_cnt,wrong_cnt)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                [(r.get("qid"), r.get("status", "new"), r.get("ease", 2.5),
                  r.get("interval", 0), r.get("reps", 0), r.get("lapses", 0),
                  r.get("due"), r.get("last"), r.get("right_cnt", 0), r.get("wrong_cnt", 0))
                 for r in srs])
            if rev:
                c.executemany(
                    "INSERT INTO reviews(qid,grade,right,ts) VALUES(?,?,?,?)",
                    [(r.get("qid"), r.get("grade", 0), r.get("right", 0), r.get("ts", "")) for r in rev])
            if fav:
                c.executemany("INSERT OR REPLACE INTO favorites(qid,added) VALUES(?,?)",
                              [(r.get("qid"), r.get("added", "")) for r in fav])
            if nts:
                c.executemany("INSERT OR REPLACE INTO notes(qid,text,updated) VALUES(?,?,?)",
                              [(r.get("qid"), r.get("text", ""), r.get("updated", "")) for r in nts])
            c.commit()
    finally:
        c.close()
    return {"ok": True, "count": len(srs)}


# ---------- SM-2 ----------

def schedule(cur, grade, today_iso):
    """grade 1=忘记 2=困难 3=一般 4=熟悉；返回新的记忆状态。"""
    ease = float(cur["ease"] or 2.5)
    iv = int(cur["interval"] or 0)
    reps = int(cur["reps"] or 0)
    lapses = int(cur["lapses"] or 0)

    if grade <= 1:
        reps = 0
        lapses += 1
        iv = 1
        ease = max(1.3, ease - 0.25)
        status = "learning"
    else:
        q = {2: 3, 3: 4, 4: 5}[grade]
        ease = max(1.3, ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)))
        reps += 1
        if reps == 1:
            iv = 1
        elif reps == 2:
            iv = 6
        else:
            iv = max(1, round(iv * ease))
        if grade == 2:
            iv = max(1, round(iv * 0.6))
        status = "review" if reps >= 2 else "learning"
    due = (date.fromisoformat(today_iso) + timedelta(days=iv)).isoformat()
    return {"ease": ease, "interval": iv, "reps": reps, "lapses": lapses,
            "due": due, "status": status}


# ---------- 查询拼装 ----------

def q_one_question(qid):
    r = one("""SELECT q.*, s.status, s.due, s.interval, s.reps, s.wrong_cnt, s.right_cnt,
                      (SELECT 1 FROM favorites f WHERE f.qid=q.qid) fav,
                      (SELECT text FROM notes n WHERE n.qid=q.qid) note
               FROM questions q LEFT JOIN srs s ON s.qid=q.qid WHERE q.qid=?""", (qid,))
    if r:
        r["options"] = json.loads(r["options"] or "[]")
    return r


def pick(mode, module="", category="", region="", n=20):
    n = max(1, min(50, n))
    where, args = ["q.answer<>''"], []
    if module:
        where.append("q.module=?"); args.append(module)
    if category:
        where.append("q.category=?"); args.append(category)
    if region:
        where.append("q.region=?"); args.append(region)

    if mode == "new":
        where.append("(s.status IS NULL OR s.status='new')")
        sql = ("SELECT q.qid FROM questions q LEFT JOIN srs s ON s.qid=q.qid "
               "WHERE " + " AND ".join(where) + " ORDER BY RANDOM() LIMIT ?")
    elif mode == "review":
        where.append("s.due IS NOT NULL AND s.due<=? AND s.status<>'new'")
        args.append(today())
        sql = ("SELECT q.qid FROM questions q JOIN srs s ON s.qid=q.qid "
               "WHERE " + " AND ".join(where) + " ORDER BY s.due LIMIT ?")
    elif mode == "wrong":
        where.append("s.wrong_cnt>0")
        sql = ("SELECT q.qid FROM questions q JOIN srs s ON s.qid=q.qid "
               "WHERE " + " AND ".join(where) + " ORDER BY s.wrong_cnt DESC, RANDOM() LIMIT ?")
    elif mode == "fav":
        where.append("f.qid IS NOT NULL")
        sql = ("SELECT q.qid FROM questions q JOIN favorites f ON f.qid=q.qid "
               "WHERE " + " AND ".join(where) + " ORDER BY RANDOM() LIMIT ?")
    else:
        return []
    args.append(n)
    qids = [r["qid"] for r in many(sql, args)]
    return [q_one_question(q) for q in qids]


# ---------- HTTP ----------

ROUTES_GET = {}


def route(path):
    def deco(fn):
        ROUTES_GET[path] = fn
        return fn
    return deco


class Handler(BaseHTTPRequestHandler):
    server_version = "HongJuan/1.0"

    def log_message(self, fmt, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, mime, max_age=0):
        """max_age=0 表示每次都回来问一句（改完代码刷新就能生效）。"""
        try:
            st = os.stat(path)
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return self._json({"error": "not found"}, 404)
        lm = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(st.st_mtime))
        if self.headers.get("If-Modified-Since") == lm:
            self.send_response(304)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Last-Modified", lm)
        if max_age:
            self.send_header("Cache-Control", "public, max-age=%d" % max_age)
        else:
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _index(self):
        """下发首页时给静态资源带上 mtime 版本号，改完 js/css 刷新必定换新。"""
        try:
            with open(os.path.join(WEB, "index.html"), "rb") as f:
                html = f.read()
            ver = int(max(os.path.getmtime(os.path.join(WEB, "app.js")),
                          os.path.getmtime(os.path.join(WEB, "style.css"))))
        except OSError:
            return self._json({"error": "not found"}, 404)
        data = html.replace(b"{{V}}", str(ver).encode())
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(u.path)
        qs = urllib.parse.parse_qs(u.query)
        g = lambda k, d="": (qs.get(k) or [d])[0]

        if path in ("/", "/index.html"):
            return self._index()
        if path.startswith("/s/"):
            name = path[3:]
            mime = {"app.js": "application/javascript; charset=utf-8",
                    "style.css": "text/css; charset=utf-8"}.get(name)
            if not mime:
                return self._json({"error": "no route"}, 404)
            return self._file(os.path.join(WEB, name), mime)
        if path.startswith("/img/"):
            rel = path[5:]
            fp = os.path.normpath(os.path.join(IMG, rel))
            if not fp.startswith(IMG):
                return self._json({"error": "forbidden"}, 403)
            if not os.path.isfile(fp):
                return self._json({"error": "missing"}, 404)
            ext = os.path.splitext(fp)[1].lower()
            mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".webp": "image/webp", ".gif": "image/gif"}.get(ext, "application/octet-stream")
            return self._file(fp, mime, max_age=2592000)
        if path.startswith("/api/"):
            try:
                return self.api(path[5:], g)
            except Exception as e:
                import traceback
                traceback.print_exc()
                return self._json({"error": str(e)}, 500)
        return self._json({"error": "no route"}, 404)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(u.path)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n).decode() or "{}")
        except Exception:
            body = {}
        if not path.startswith("/api/"):
            return self._json({"error": "no route"}, 404)
        try:
            return self.api(path[5:], lambda k, d="": body.get(k, d), body)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return self._json({"error": str(e)}, 500)

    # ---- 接口 ----

    def api(self, name, g, body=None):
        if name == "overview":
            return self._json(self.overview())
        if name == "pick":
            return self._json({"list": pick(g("mode", "new"), g("module"), g("category"),
                                            g("region"), int(g("n", 20) or 20))})
        if name == "question":
            r = q_one_question(g("qid"))
            return self._json(r or {"error": "no such question"}, 200 if r else 404)
        if name == "browse":
            return self._json(self.browse(g))
        if name == "stats":
            return self._json(self.stats())
        if name == "facets":
            return self._json(self.facets())
        if name == "grade":
            return self._json(self.grade(body))
        if name == "fav":
            qid = body.get("qid")
            if body.get("on"):
                write("INSERT OR REPLACE INTO favorites(qid,added) VALUES(?,?)", (qid, today()))
            else:
                write("DELETE FROM favorites WHERE qid=?", (qid,))
            return self._json({"ok": True})
        if name == "note":
            qid, text = body.get("qid"), (body.get("text") or "").strip()
            if text:
                write("INSERT OR REPLACE INTO notes(qid,text,updated) VALUES(?,?,?)",
                      (qid, text, today()))
            else:
                write("DELETE FROM notes WHERE qid=?", (qid,))
            return self._json({"ok": True})
        if name == "export":
            return self._json(export_progress())
        if name == "import":
            return self._json(import_progress(body or {}))
        return self._json({"error": "no such api"}, 404)

    def overview(self):
        t = today()
        d = one("""SELECT
              (SELECT COUNT(*) FROM srs WHERE due<=? AND status<>'new') due,
              (SELECT COUNT(*) FROM srs WHERE status IN ('learning','review')) learned,
              (SELECT COUNT(*) FROM srs WHERE wrong_cnt>0) wrong,
              (SELECT COUNT(*) FROM favorites) fav,
              (SELECT COUNT(*) FROM reviews WHERE substr(ts,1,10)=?) today_done,
              (SELECT COUNT(*) FROM reviews WHERE substr(ts,1,10)=? AND right=1) today_right
            """, (t, t, t))
        d["total"] = one("SELECT COUNT(*) n FROM questions")["n"]
        d["new_left"] = d["total"] - d["learned"]
        d["streak"] = self.streak()
        # 各模块进度，给首页画格子用
        d["modules"] = many("""SELECT q.module,
                 COUNT(DISTINCT q.qid) total,
                 COUNT(DISTINCT CASE WHEN s.status IN ('learning','review') THEN q.qid END) done,
                 COUNT(DISTINCT CASE WHEN s.due<=? AND s.status<>'new' THEN q.qid END) due
               FROM questions q LEFT JOIN srs s ON s.qid=q.qid
               GROUP BY q.module ORDER BY total DESC""", (t,))
        return d

    def streak(self):
        rows = [r["d"] for r in many(
            "SELECT DISTINCT substr(ts,1,10) d FROM reviews ORDER BY d DESC LIMIT 400")]
        if not rows:
            return 0
        n, cur = 0, date.today()
        if rows[0] != cur.isoformat():
            cur = cur - timedelta(days=1)
        s = set(rows)
        while cur.isoformat() in s:
            n += 1
            cur -= timedelta(days=1)
        return n

    def browse(self, g):
        page = max(1, int(g("page", 1) or 1))
        size = 20
        where, args = ["1=1"], []
        for k, col in (("module", "q.module"), ("category", "q.category"),
                       ("year", "q.year"), ("region", "q.region")):
            v = g(k)
            if v:
                where.append(col + "=?"); args.append(v)
        kw = (g("kw") or "").strip()
        if kw:
            where.append("(q.stem LIKE ? OR q.analysis LIKE ?)")
            args += ["%" + kw + "%"] * 2
        cond = " AND ".join(where)
        total = one("SELECT COUNT(*) n FROM questions q WHERE " + cond, args)["n"]
        rows = many("""SELECT q.qid,q.module,q.category,q.year,q.region,q.paper,
                              substr(replace(q.stem,'<p>',''),1,90) brief,
                              s.status,s.due,s.wrong_cnt,
                              (SELECT 1 FROM favorites f WHERE f.qid=q.qid) fav
                       FROM questions q LEFT JOIN srs s ON s.qid=q.qid
                       WHERE """ + cond + " ORDER BY q.year DESC, q.qid LIMIT ? OFFSET ?",                    args + [size, (page - 1) * size])
        for r in rows:
            r["brief"] = re.sub(r"<[^>]+>", "", r["brief"] or "").strip()
        return {"total": total, "page": page, "size": size, "list": rows}

    def facets(self):
        return {
            "modules": [r["module"] for r in many(
                "SELECT module FROM questions GROUP BY module ORDER BY COUNT(*) DESC")],
            "categories": many("SELECT module,category,COUNT(*) n FROM questions "
                               "GROUP BY module,category ORDER BY n DESC"),
            "years": [r["year"] for r in many(
                "SELECT year FROM questions GROUP BY year ORDER BY year DESC")],
            "regions": [r["region"] for r in many(
                "SELECT region FROM questions GROUP BY region ORDER BY COUNT(*) DESC")],
            "region_counts": many("SELECT region, COUNT(*) n FROM questions "
                                  "WHERE region<>'' GROUP BY region ORDER BY n DESC"),
        }

    def grade(self, body):
        qid = body.get("qid")
        picked = "".join(sorted(set(body.get("picked") or [])))
        q = one("SELECT answer FROM questions WHERE qid=?", (qid,))
        if not q:
            return {"error": "no such question"}
        right = "".join(sorted(set(q["answer"] or ""))) == picked
        grade = int(body.get("grade") or 0)
        if grade not in (1, 2, 3, 4):
            grade = 3 if right else 1
        cur = one("SELECT * FROM srs WHERE qid=?", (qid,)) or {
            "ease": 2.5, "interval": 0, "reps": 0, "lapses": 0}
        s = schedule(cur, grade, today())
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        c = conn()
        try:
            with _lock:
                c.execute("""INSERT INTO srs(qid,status,ease,interval,reps,lapses,due,last,right_cnt,wrong_cnt)
                             VALUES(?,?,?,?,?,?,?,?,?,?)
                             ON CONFLICT(qid) DO UPDATE SET
                               status=excluded.status, ease=excluded.ease, interval=excluded.interval,
                               reps=excluded.reps, lapses=excluded.lapses, due=excluded.due,
                               last=excluded.last,
                               right_cnt=srs.right_cnt+excluded.right_cnt,
                               wrong_cnt=srs.wrong_cnt+excluded.wrong_cnt""",
                          (qid, s["status"], s["ease"], s["interval"], s["reps"], s["lapses"],
                           s["due"], ts, 1 if right else 0, 0 if right else 1))
                c.execute("INSERT INTO reviews(qid,grade,right,ts) VALUES(?,?,?,?)",
                          (qid, grade, 1 if right else 0, ts))
                c.commit()
        finally:
            c.close()
        return {"ok": True, "right": right, "answer": q["answer"], "due": s["due"],
                "interval": s["interval"], "status": s["status"]}

    def stats(self):
        t = today()
        d = {}
        d["modules"] = many("""SELECT q.module,
                 COUNT(DISTINCT q.qid) total,
                 COUNT(DISTINCT CASE WHEN s.status IN ('learning','review') THEN q.qid END) done,
                 COUNT(DISTINCT CASE WHEN s.wrong_cnt>0 THEN q.qid END) wrong
               FROM questions q LEFT JOIN srs s ON s.qid=q.qid GROUP BY q.module ORDER BY total DESC""")
        d["recent"] = many("""SELECT substr(ts,1,10) d, COUNT(*) n,
                                SUM(right) right_n
                              FROM reviews WHERE substr(ts,1,10)>=?
                              GROUP BY d ORDER BY d""",
                           ((date.today() - timedelta(days=29)).isoformat(),))
        d["weak"] = many("""SELECT q.category, COUNT(*) n FROM srs s JOIN questions q ON q.qid=s.qid
                            WHERE s.wrong_cnt>0 GROUP BY q.category ORDER BY n DESC LIMIT 8""")
        d["funnel"] = one("""SELECT
                     SUM(CASE WHEN status='new' OR status IS NULL THEN 1 ELSE 0 END) new_n,
                     SUM(CASE WHEN status='learning' THEN 1 ELSE 0 END) learning_n,
                     SUM(CASE WHEN status='review' THEN 1 ELSE 0 END) review_n
                   FROM srs""") or {}
        d["total"] = one("SELECT COUNT(*) n FROM questions")["n"]
        d["done_total"] = one("SELECT COUNT(*) n FROM reviews")["n"]
        d["today"] = t
        return d


def main():
    if not os.path.exists(DB):
        print("[错误] 找不到 hongjuan.db，先跑 python build_db.py")
        sys.exit(1)
    if not os.path.isdir(IMG):
        print("[提醒] 图片目录不存在：", IMG, "（题目图会裂，文字正常）")
    print("行测红卷 → http://127.0.0.1:%d" % PORT)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
