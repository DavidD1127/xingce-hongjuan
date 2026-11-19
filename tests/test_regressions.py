"""使用临时库测试，绝不写入用户题库或手机。"""
import contextlib
import http.client
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "test.db"
        self.build(ROOT / "sample", check=True)
        self.old_db = server.DB
        server.DB = str(self.db)
        self.addCleanup(setattr, server, "DB", self.old_db)
        self.qid = server.one("SELECT qid FROM questions LIMIT 1")["qid"]

    def build(self, vault, check=False):
        return subprocess.run([sys.executable, str(ROOT / "build_db.py"), str(vault),
                               "--out", str(self.db)], capture_output=True, check=check)

    def seed(self):
        server.write("INSERT INTO notes VALUES(?,?,?)", (self.qid, "保留笔记", "2026-11-19"))

    def start_http(self):
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd.server_address[1]

    def request(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            c.request(method, path, body, headers or {})
            response = c.getresponse()
            return response.status, response.read()
        finally:
            c.close()

    def test_sample_has_twelve_questions(self):
        self.assertEqual(server.one("SELECT COUNT(*) n FROM questions")["n"], 12)

    def test_material_applies_to_eight_questions(self):
        import build_db
        path = Path(self.tmp.name) / "material.md"
        path.write_text("### 材料 1\n材料正文\n" + "".join(
            "### 第 %d 题 <sub>qid %d · 考点</sub>\n题干\n**答案**：A\n" % (i, i)
            for i in range(1, 10)), encoding="utf-8")
        qs, _ = build_db.parse_file(path, "资料分析")
        self.assertTrue(all(q["mid"] for q in qs[:8]))
        self.assertFalse(qs[8]["mid"])

    def test_rebuild_preserves_progress(self):
        self.seed()
        self.build(ROOT / "sample", check=True)
        self.assertEqual(server.one("SELECT text FROM notes")["text"], "保留笔记")

    def test_empty_source_preserves_database(self):
        self.seed()
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        self.assertNotEqual(self.build(empty).returncode, 0)
        self.assertEqual(server.one("SELECT COUNT(*) n FROM questions")["n"], 12)
        self.assertEqual(server.one("SELECT text FROM notes")["text"], "保留笔记")

    def test_failed_rebuild_rolls_back_question_changes(self):
        self.seed()
        server.write("CREATE TRIGGER fail_insert BEFORE INSERT ON questions "
                     "BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        self.assertNotEqual(self.build(ROOT / "sample").returncode, 0)
        self.assertEqual(server.one("SELECT COUNT(*) n FROM questions")["n"], 12)
        self.assertEqual(server.one("SELECT text FROM notes")["text"], "保留笔记")

    def test_import_rejects_unrelated_json_without_clearing(self):
        self.seed()
        result = server.import_progress({"notes": [{"qid": self.qid, "text": "无关"}]})
        self.assertIn("error", result)
        self.assertEqual(server.one("SELECT text FROM notes")["text"], "保留笔记")

    def test_import_roundtrip_and_rollback(self):
        self.seed()
        exported = server.export_progress()
        self.assertTrue(server.import_progress(exported)["ok"])
        exported["reviews"] = [{"qid": self.qid, "grade": None}]
        with self.assertRaises(sqlite3.IntegrityError):
            server.import_progress(exported)
        self.assertEqual(server.one("SELECT text FROM notes")["text"], "保留笔记")

    def test_grade_review_and_wrong_queue(self):
        handler = object.__new__(server.Handler)
        result = handler.grade({"qid": self.qid, "picked": [], "grade": 1})
        self.assertTrue(result["ok"])
        self.assertFalse(result["right"])
        self.assertEqual(result["interval"], 1)
        self.assertEqual(server.pick("review"), [])
        self.assertEqual(server.pick("wrong")[0]["qid"], self.qid)
        self.assertEqual(len(server.export_progress()["reviews"]), 1)
        row = handler.browse(lambda key, default="": default)["list"]
        self.assertEqual(next(r for r in row if r["qid"] == self.qid)["interval"], 1)

    def test_http_core_routes(self):
        self.port = self.start_http()
        for path in ("/", "/s/app.js", "/s/style.css", "/api/overview", "/api/facets",
                     "/api/pick", "/api/browse", "/api/stats", "/api/export"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 200)

    def test_http_invalid_json_and_get_write(self):
        self.port = self.start_http()
        self.assertEqual(self.request("POST", "/api/note", "[")[0], 400)
        self.assertEqual(self.request("POST", "/api/note", "[]")[0], 400)
        self.assertEqual(self.request("GET", "/api/grade")[0], 405)
        self.assertEqual(self.request("POST", "/api/note", "{}", {"Origin": "https://other.test"})[0], 403)

    def test_image_sibling_path_is_forbidden(self):
        root = Path(self.tmp.name) / "images"
        sibling = Path(self.tmp.name) / "images-private"
        root.mkdir()
        sibling.mkdir()
        (sibling / "secret.txt").write_text("secret")
        old = server.IMG
        server.IMG = str(root)
        self.addCleanup(setattr, server, "IMG", old)
        self.port = self.start_http()
        self.assertEqual(self.request("GET", "/img/../images-private/secret.txt")[0], 403)

    def test_apk_without_images_is_clean_and_versioned(self):
        try:
            import PIL
        except ImportError:
            self.skipTest("APK 资源测试需要 Pillow")
        import build_apk
        self.seed()
        with contextlib.ExitStack() as stack:
            for name, value in (("DB_SRC", str(self.db)), ("ASSETS", str(Path(self.tmp.name) / "assets"))):
                old = getattr(build_apk, name)
                setattr(build_apk, name, value)
                stack.callback(setattr, build_apk, name, old)
            out = build_apk.rewrite_db({})
            with contextlib.closing(sqlite3.connect(out)) as c:
                self.assertEqual(c.execute("SELECT COUNT(*) FROM notes").fetchone()[0], 0)
            self.assertTrue((Path(out).parent / "build.txt").is_file())
        self.assertEqual(server.one("SELECT text FROM notes")["text"], "保留笔记")


if __name__ == "__main__":
    unittest.main()
