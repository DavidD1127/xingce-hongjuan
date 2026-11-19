# -*- coding: utf-8 -*-
"""
行测红卷 · 题库导入器
把上游 Obsidian 题库（D:\\AI\\xingcezhenti）的 Markdown 真题笔记，导成一个 SQLite 文件。

用法：
    python build_db.py            # 默认读 D:\\AI\\xingcezhenti，产出 hongjuan.db
    python build_db.py <vault>    # 指定题库目录

题目按 qid 去重：同 qid 只留一条，并记下它被多少套卷收录。
"""
import json
import os
import re
import sqlite3
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))


def parse_args():
    """第一个位置参数是题库目录，--out 指定输出文件（默认 ./hongjuan.db）。"""
    vault = r"D:\AI\xingcezhenti"
    out = os.path.join(HERE, "hongjuan.db")
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--out" and i + 1 < len(args):
            out = args[i + 1]
            i += 2
            continue
        if not a.startswith("--"):
            vault = a
        i += 1
    return vault, out


VAULT, DB = parse_args()
MODULES = ["01-政治理论", "02-常识判断", "03-言语理解与表达",
           "04-数量关系", "05-判断推理", "06-资料分析"]

SCHEMA = """
CREATE TABLE questions(
    qid       TEXT PRIMARY KEY,
    module    TEXT NOT NULL,
    category  TEXT,
    paper     TEXT,
    region    TEXT,
    year      TEXT,
    stem      TEXT,
    options   TEXT,
    answer    TEXT,
    analysis  TEXT,
    material  TEXT,
    mid       TEXT,
    n_papers  INTEGER DEFAULT 1,
    papers    TEXT
);
CREATE TABLE materials(
    mid   TEXT PRIMARY KEY,
    title TEXT,
    body  TEXT
);
CREATE TABLE srs(
    qid       TEXT PRIMARY KEY,
    status    TEXT DEFAULT 'new',
    ease      REAL DEFAULT 2.5,
    interval  INTEGER DEFAULT 0,
    reps      INTEGER DEFAULT 0,
    lapses    INTEGER DEFAULT 0,
    due       TEXT,
    last      TEXT,
    right_cnt INTEGER DEFAULT 0,
    wrong_cnt INTEGER DEFAULT 0
);
CREATE TABLE reviews(
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    qid     TEXT NOT NULL,
    grade   INTEGER NOT NULL,
    right   INTEGER NOT NULL DEFAULT 0,
    ts      TEXT NOT NULL
);
CREATE TABLE favorites(
    qid   TEXT PRIMARY KEY,
    added TEXT
);
CREATE TABLE notes(
    qid     TEXT PRIMARY KEY,
    text    TEXT,
    updated TEXT
);
CREATE TABLE settings(
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE INDEX ix_q_module ON questions(module, category);
CREATE INDEX ix_srs_due ON srs(due);
CREATE INDEX ix_rev_ts ON reviews(ts);
"""

RE_HEAD = re.compile(r"^#{2,3}\s*(第\s*(\d+)\s*题|材料\s*(\d+))\s*(.*)$")
RE_QID = re.compile(r"qid\s+(\S+?)\s*·\s*(.*?)</sub>")
RE_OPT = re.compile(r"^-\s*\*\*([A-E])\*\*\.\s*(.*)$")
RE_ANS = re.compile(r"^\*\*答案\*\*[：:]\s*(.+?)\s*$")
RE_FM = re.compile(r'^(\S+?):\s*"?(.*?)"?\s*$')


def frontmatter(text):
    """取文件头的 key: "value" 段。"""
    meta = {}
    if not text.startswith("---"):
        return meta
    end = text.find("\n---", 3)
    if end < 0:
        return meta
    for line in text[3:end].split("\n"):
        m = RE_FM.match(line.strip())
        if m:
            meta[m.group(1)] = m.group(2)
    return meta


def fix_html(s):
    """把图片路径改成本站路径，顺手清掉目录前缀。"""
    if not s:
        return ""
    s = s.replace('src="../90-图片/', 'src="/img/')
    s = s.replace('src="90-图片/', 'src="/img/')
    return s.strip()


def parse_file(path, module):
    """解析一篇笔记，产出 (题目列表, 材料字典)。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    meta = frontmatter(text)

    lines = text.split("\n")
    questions = []
    materials = {}
    cur = None          # 当前题块的行
    cur_no = None
    cur_mid = None      # 当前材料编号
    cur_left = 0        # 这份材料还管几题
    mat = None          # 正在收集的材料体

    # 一份材料实际配 4-5 道题，偶尔到 8。题库里有些卷子只写了「材料 2」，
    # 后面几十道普通题也算在它名下——不设上限的话，一道文化多样性题会顶着
    # 「小鼠换血」的材料。宁可能少挂，也别一路挂到卷尾。
    MAX_PER_MATERIAL = 8

    def flush_mat():
        if mat is not None and cur_mid:
            materials[mat["mid"]] = {"title": mat["title"], "body": fix_html("\n".join(mat["lines"]))}

    def flush_q():
        if cur is None:
            return
        q = build_question(cur, module, meta, cur_mid)
        if q:
            questions.append(q)

    for raw in lines:
        m = RE_HEAD.match(raw)
        if m:
            if m.group(3):                       # 材料头
                flush_q(); cur = None
                flush_mat(); mat = None
                # 文件名也要进来：同一份卷子常拆成好几篇笔记，各自都有「材料 2」，
                # 只用 模块|试卷|编号 会让后面的把前面的覆盖掉，题干和材料就对不上了
                cur_mid = "%s|%s|%s|%s" % (module, meta.get("试卷", ""),
                                           os.path.basename(path), m.group(3))
                mat = {"mid": cur_mid, "title": "材料 %s" % m.group(3), "lines": []}
                cur_left = 0
                continue
            if m.group(2):                       # 题头（qid 就写在这一行里）
                flush_q()
                if mat is not None:
                    flush_mat(); mat = None
                    cur_left = MAX_PER_MATERIAL
                cur = [m.group(4) or ""]
                if cur_mid is not None:
                    cur_left -= 1
                    if cur_left < 0:
                        cur_mid = None
                continue
        if mat is not None:
            mat["lines"].append(raw)
        elif cur is not None:
            cur.append(raw)

    flush_q()
    flush_mat()
    return questions, materials


def build_question(lines, module, meta, mid):
    head = lines[0] if lines else ""
    mq = RE_QID.search(head)
    qid = mq.group(1) if mq else ""
    category = (mq.group(2).strip() if mq else "") or "未分类"
    if not re.fullmatch(r"\d+", qid or ""):
        return None

    body = lines[1:]
    # 切段：题干 / 选项 / 答案 / 解析
    stem, opts, answer, analysis = [], [], "", []
    stage = "stem"
    for ln in body:
        s = ln.strip()
        if stage == "stem":
            if RE_OPT.match(s):
                stage = "opt"
            elif RE_ANS.match(s):
                stage = "ana"
                answer = RE_ANS.match(s).group(1)
                continue
            elif s == "**官方解析**":
                stage = "ana"
                continue
            elif s == "---":
                continue
        if stage == "opt":
            mo = RE_OPT.match(s)
            if mo:
                label = mo.group(2).replace("　✅", "").replace("✅", "").strip()
                opts.append({"k": mo.group(1), "v": fix_html(label)})
                continue
            if RE_ANS.match(s):
                answer = RE_ANS.match(s).group(1)
                stage = "ana"
                continue
            if s == "":
                continue
            # 选项里换行续写的 HTML，接上一项
            if opts and s != "---":
                opts[-1]["v"] += fix_html(s)
            continue
        if stage == "ana":
            if s == "---" or s.startswith("## "):
                break
            if s == "**官方解析**":
                continue
            analysis.append(ln)
        else:
            if s == "---":
                continue
            stem.append(ln)

    ans = re.sub(r"[^A-H]", "", answer or "")[:6]
    if not opts:
        # 判断题：原文没有选项，A=正确 B=错误
        opts = [{"k": "A", "v": "正确"}, {"k": "B", "v": "错误"}]
    return {
        "qid": qid,
        "module": module,
        "category": category,
        "paper": meta.get("试卷", ""),
        "region": meta.get("地区", ""),
        "year": meta.get("年份", ""),
        "stem": fix_html("\n".join(stem)),
        "options": json.dumps(opts, ensure_ascii=False),
        "answer": ans,
        "analysis": fix_html("\n".join(analysis)),
        "mid": mid or "",
    }


def main():
    if not os.path.isdir(VAULT):
        print("[错误] 题库目录不存在：", VAULT)
        sys.exit(1)
    t0 = time.time()
    total_blocks = 0
    files = 0
    mats = {}
    rows = {}            # qid -> row，用来去重
    for mod_dir in MODULES:
        d = os.path.join(VAULT, mod_dir)
        if not os.path.isdir(d):
            print("[跳过] 缺目录", mod_dir)
            continue
        module = mod_dir.split("-", 1)[1]
        for name in sorted(os.listdir(d)):
            if not name.endswith(".md"):
                continue
            qs, ms = parse_file(os.path.join(d, name), module)
            files += 1
            total_blocks += len(qs)
            mats.update(ms)
            for q in qs:
                old = rows.get(q["qid"])
                if old:
                    old["n_papers"] += 1
                    if q["paper"] not in old["papers"]:
                        old["papers"].append(q["paper"])
                else:
                    q["n_papers"] = 1
                    q["papers"] = [q["paper"]]
                    rows[q["qid"]] = q
        print("  已读 %-16s 累计 %d 题" % (module, len(rows)))

    if not rows:
        raise SystemExit("[失败] 一道题也没导入，原数据库未修改；请检查题库目录，或使用 sample。")

    # 先完整解析，再在同一事务内换题；保留按稳定 qid 关联的学习记录。
    con = sqlite3.connect(DB, timeout=10)
    con.executescript(SCHEMA.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ")
                     .replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS "))
    con.execute("BEGIN IMMEDIATE")
    con.execute("DELETE FROM questions")
    con.execute("DELETE FROM materials")
    con.executemany(
        "INSERT INTO materials(mid,title,body) VALUES(?,?,?)",
        [(k, v["title"], v["body"]) for k, v in mats.items()])
    con.executemany(
        """INSERT INTO questions(qid,module,category,paper,region,year,stem,options,
                                answer,analysis,material,mid,n_papers,papers)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [(q["qid"], q["module"], q["category"], q["paper"], q["region"], q["year"],
          q["stem"], q["options"], q["answer"], q["analysis"], "", q["mid"],
          q["n_papers"], "、".join(q["papers"][:3]))
         for q in rows.values()])
    # 把材料正文回填到题上，前端一次取回就能渲染
    con.execute("""UPDATE questions SET material=(
                     SELECT body FROM materials WHERE materials.mid=questions.mid)
                   WHERE mid<>''""")
    con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('built_at',?)",
                (time.strftime("%Y-%m-%d %H:%M:%S"),))
    con.commit()

    n = con.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    nm = con.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
    print()
    print("文件 %d 篇 / 题块 %d / 去重后 %d 题 / 材料组 %d" % (files, total_blocks, n, nm))
    for mod, c in con.execute("SELECT module,COUNT(*) FROM questions GROUP BY module ORDER BY 2 DESC"):
        print("  %-10s %6d" % (mod, c))
    print("用时 %.1fs，库大小 %.1f MB" % (time.time() - t0, os.path.getsize(DB) / 1048576))
    con.close()

if __name__ == "__main__":
    main()
