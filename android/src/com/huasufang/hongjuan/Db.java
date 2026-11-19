package com.huasufang.hongjuan;

import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteStatement;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * 题库与学习记录。SQL 与桌面版 server.py 保持一致，只是换成了本地数据库。
 */
public class Db {
    private final Context ctx;
    private SQLiteDatabase db;
    private final Object writeLock = new Object();
    private final SimpleDateFormat df = new SimpleDateFormat("yyyy-MM-dd", Locale.US);

    Db(Context c) {
        ctx = c;
    }

    /** 首次启动把随包带的题库拷到应用私有目录；题库换了就迁移学习记录。 */
    void ensure() {
        File f = ctx.getDatabasePath("hongjuan.db");
        String want = assetText("db/build.txt");
        if (f.exists()) {
            if (want.length() == 0) return;                 // 旧包没有版本号，保持原样
            if (want.equals(settingRead(f, "db_build"))) return;
            // 题库版本变了：先把旧库留一份，拷新库，再把做题记录搬过去
            File bak = new File(f.getPath() + ".bak");
            if (bak.exists() && !bak.delete()) return;      // 备份失败就不动，宁可先用旧库
            if (!f.renameTo(bak)) {
                return;
            }
            try {
                copyAssetDb(f);
                migrate(bak, f);
                settingWrite(f, "db_build", want);
            } catch (RuntimeException e) {
                // 新库或迁移失败时回到旧库，备份恢复失败则保留备份并明确报错。
                if (f.exists() && !f.delete()) throw e;
                if (!bak.renameTo(f)) throw e;
                android.util.Log.e("HJ", "题库更新失败，已恢复原库", e);
            }
            return;
        }
        copyAssetDb(f);
        if (want.length() > 0) settingWrite(f, "db_build", want);
    }

    private String assetText(String path) {
        InputStream in = null;
        try {
            in = ctx.getAssets().open(path);
            byte[] buf = new byte[256];
            int n = in.read(buf);
            return n <= 0 ? "" : new String(buf, 0, n, "UTF-8").trim();
        } catch (IOException e) {
            return "";
        } finally {
            close(in);
        }
    }

    private String settingRead(File dbFile, String key) {
        SQLiteDatabase d = null;
        Cursor c = null;
        try {
            d = SQLiteDatabase.openDatabase(dbFile.getPath(), null, SQLiteDatabase.OPEN_READONLY);
            c = d.rawQuery("SELECT value FROM settings WHERE key=?", new String[]{key});
            return c.moveToFirst() ? c.getString(0) : "";
        } catch (Exception e) {
            return "";
        } finally {
            if (c != null) c.close();
            if (d != null) d.close();
        }
    }

    private void settingWrite(File dbFile, String key, String value) {
        SQLiteDatabase d = null;
        try {
            d = SQLiteDatabase.openDatabase(dbFile.getPath(), null, SQLiteDatabase.OPEN_READWRITE);
            d.execSQL("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", new Object[]{key, value});
        } catch (Exception ignored) {
        } finally {
            if (d != null) d.close();
        }
    }

    /** 把旧库里的 srs / reviews / favorites / notes 搬进新库。题号是稳定键，直接照抄。 */
    private void migrate(File oldDb, File newDb) {
        SQLiteDatabase d = null;
        try {
            d = SQLiteDatabase.openDatabase(newDb.getPath(), null, SQLiteDatabase.OPEN_READWRITE);
            d.execSQL("ATTACH DATABASE ? AS old", new Object[]{oldDb.getPath()});
            d.beginTransaction();
            try {
            d.execSQL("INSERT OR REPLACE INTO srs(qid,status,ease,interval,reps,lapses,due,last,right_cnt,wrong_cnt)" +
                    " SELECT qid,status,ease,interval,reps,lapses,due,last,right_cnt,wrong_cnt FROM old.srs");
            d.execSQL("INSERT OR IGNORE INTO favorites(qid,added) SELECT qid,added FROM old.favorites");
            d.execSQL("INSERT OR REPLACE INTO notes(qid,text,updated) SELECT qid,text,updated FROM old.notes");
            d.execSQL("INSERT INTO reviews(qid,grade,right,ts) SELECT qid,grade,right,ts FROM old.reviews");
                d.setTransactionSuccessful();
            } finally {
                d.endTransaction();
            }
            d.execSQL("DETACH DATABASE old");
        } catch (Exception e) {
            throw new RuntimeException("学习记录迁移失败", e);
        } finally {
            if (d != null) d.close();
        }
    }

    private void copyAssetDb(File f) {
        File dir = f.getParentFile();
        if (dir != null) dir.mkdirs();
        InputStream in = null;
        OutputStream out = null;
        try {
            in = ctx.getAssets().open("db/hongjuan.db");
            out = new FileOutputStream(f);
            byte[] buf = new byte[1 << 16];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            out.flush();
        } catch (IOException e) {
            throw new RuntimeException("题库复制失败：" + e.getMessage(), e);
        } finally {
            close(in);
            close(out);
        }
    }

    private void close(java.io.Closeable c) {
        try {
            if (c != null) c.close();
        } catch (IOException ignored) {
        }
    }

    private SQLiteDatabase db() {
        if (db == null || !db.isOpen()) {
            db = SQLiteDatabase.openDatabase(
                    ctx.getDatabasePath("hongjuan.db").getAbsolutePath(), null,
                    SQLiteDatabase.OPEN_READWRITE);
        }
        return db;
    }

    private String today() {
        return df.format(new Date());
    }

    // ---------- 查表工具 ----------

    private List<JSONObject> rows(String sql, String... args) {
        List<JSONObject> out = new ArrayList<JSONObject>();
        Cursor c = db().rawQuery(sql, args);
        try {
            while (c.moveToNext()) {
                JSONObject o = new JSONObject();
                for (int i = 0; i < c.getColumnCount(); i++) {
                    String k = c.getColumnName(i);
                    try {
                        switch (c.getType(i)) {
                            case Cursor.FIELD_TYPE_INTEGER:
                                o.put(k, c.getLong(i));
                                break;
                            case Cursor.FIELD_TYPE_FLOAT:
                                o.put(k, c.getDouble(i));
                                break;
                            case Cursor.FIELD_TYPE_NULL:
                                o.put(k, JSONObject.NULL);
                                break;
                            default:
                                o.put(k, c.getString(i));
                        }
                    } catch (Exception e) {
                        throw new RuntimeException(e);
                    }
                }
                out.add(o);
            }
        } finally {
            c.close();
        }
        return out;
    }

    private JSONObject row(String sql, String... args) {
        List<JSONObject> r = rows(sql, args);
        return r.isEmpty() ? null : r.get(0);
    }

    private long count(String sql, String... args) {
        JSONObject o = row(sql, args);
        if (o == null) return 0;
        Object v = o.opt("n");
        return v instanceof Number ? ((Number) v).longValue() : 0;
    }

    // ---------- 接口分发 ----------

    String handle(String path, String bodyJson) {
        int q = path.indexOf('?');
        String name = q < 0 ? path : path.substring(0, q);
        Map<String, String> p = q < 0 ? new HashMap<String, String>() : query(path.substring(q + 1));
        JSONObject body = new JSONObject();
        try {
            if (bodyJson != null && bodyJson.length() > 0) body = new JSONObject(bodyJson);
        } catch (Exception ignored) {
        }
        try {
            String out;
            if (name.endsWith("overview")) out = overview().toString();
            else if (name.endsWith("facets")) out = facets().toString();
            else if (name.endsWith("pick")) out = pick(p).toString();
            else if (name.endsWith("question")) out = question(p.get("qid")).toString();
            else if (name.endsWith("browse")) out = browse(p).toString();
            else if (name.endsWith("stats")) out = stats().toString();
            else if (name.endsWith("grade")) out = grade(body).toString();
            else if (name.endsWith("fav")) out = fav(body).toString();
            else if (name.endsWith("note")) out = note(body).toString();
            else if (name.endsWith("export")) out = exportData().toString();
            else if (name.endsWith("import")) out = importData(body).toString();
            else out = new JSONObject().put("__error", "unknown api " + name).toString();
            return fixImg(out);
        } catch (Exception e) {
            try {
                return new JSONObject().put("__error", String.valueOf(e)).toString();
            } catch (Exception ignored) {
                return "{\"__error\":\"unknown\"}";
            }
        }
    }

    /** 图片路径换成页面同源的地址，WebView 里由 shouldInterceptRequest 从 assets 取。 */
    private String fixImg(String json) {
        return json.replace("/img/", "https://app.local/img/");
    }

    private Map<String, String> query(String qs) {
        Map<String, String> m = new HashMap<String, String>();
        for (String kv : qs.split("&")) {
            if (kv.isEmpty()) continue;
            int i = kv.indexOf('=');
            String k = i < 0 ? kv : kv.substring(0, i);
            String v = i < 0 ? "" : kv.substring(i + 1);
            try {
                m.put(k, java.net.URLDecoder.decode(v, "UTF-8"));
            } catch (Exception e) {
                m.put(k, v);
            }
        }
        return m;
    }

    private String get(Map<String, String> p, String k, String def) {
        String v = p.get(k);
        return v == null ? def : v;
    }

    private String q(String s) {
        return s == null ? "" : java.net.URLEncoder.encode(s).replace("+", "%20");
    }

    // ---------- 概览 ----------

    private JSONObject overview() {
        String t = today();
        JSONObject d = new JSONObject();
        try {
            JSONObject c = row(
                    "SELECT (SELECT COUNT(*) FROM srs WHERE due<=? AND status<>'new') due," +
                            " (SELECT COUNT(*) FROM srs WHERE status IN ('learning','review')) learned," +
                            " (SELECT COUNT(*) FROM srs WHERE wrong_cnt>0) wrong," +
                            " (SELECT COUNT(*) FROM favorites) fav," +
                            " (SELECT COUNT(*) FROM reviews WHERE substr(ts,1,10)=?) today_done," +
                            " (SELECT COUNT(*) FROM reviews WHERE substr(ts,1,10)=? AND right=1) today_right",
                    t, t, t);
            JSONObject o = c == null ? new JSONObject() : c;
            d.put("due", o.optInt("due"));
            d.put("learned", o.optInt("learned"));
            d.put("wrong", o.optInt("wrong"));
            d.put("fav", o.optInt("fav"));
            d.put("today_done", o.optInt("today_done"));
            d.put("today_right", o.optInt("today_right"));
            long total = count("SELECT COUNT(*) n FROM questions");
            d.put("total", total);
            d.put("new_left", total - o.optInt("learned"));
            d.put("streak", streak());
            d.put("modules", new JSONArray(rows(
                    "SELECT q.module, COUNT(DISTINCT q.qid) total," +
                            " COUNT(DISTINCT CASE WHEN s.status IN ('learning','review') THEN q.qid END) done," +
                            " COUNT(DISTINCT CASE WHEN s.due<=? AND s.status<>'new' THEN q.qid END) due" +
                            " FROM questions q LEFT JOIN srs s ON s.qid=q.qid" +
                            " GROUP BY q.module ORDER BY total DESC", t).toString()));
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
        return d;
    }

    private int streak() {
        List<JSONObject> r = rows("SELECT DISTINCT substr(ts,1,10) d FROM reviews ORDER BY d DESC LIMIT 400");
        if (r.isEmpty()) return 0;
        List<String> days = new ArrayList<String>();
        for (JSONObject o : r) days.add(o.optString("d"));
        Calendar cal = Calendar.getInstance();
        String cur = today();
        if (!days.get(0).equals(cur)) {
            cal.add(Calendar.DAY_OF_MONTH, -1);
            cur = df.format(cal.getTime());
        }
        int n = 0;
        while (days.contains(cur)) {
            n++;
            cal.setTime(parse(cur));
            cal.add(Calendar.DAY_OF_MONTH, -1);
            cur = df.format(cal.getTime());
        }
        return n;
    }

    private Date parse(String s) {
        try {
            return df.parse(s);
        } catch (Exception e) {
            return new Date();
        }
    }

    // ---------- 出题 ----------

    private JSONObject pick(Map<String, String> p) {
        int n = 20;
        try {
            n = Integer.parseInt(get(p, "n", "20"));
        } catch (Exception ignored) {
        }
        if (n < 1) n = 1;
        if (n > 50) n = 50;
        String mode = get(p, "mode", "new");
        String module = get(p, "module", "");
        String category = get(p, "category", "");
        String region = get(p, "region", "");

        List<String> where = new ArrayList<String>();
        List<String> args = new ArrayList<String>();
        where.add("q.answer<>''");
        if (!module.isEmpty()) {
            where.add("q.module=?");
            args.add(module);
        }
        if (!category.isEmpty()) {
            where.add("q.category=?");
            args.add(category);
        }
        if (!region.isEmpty()) {
            where.add("q.region=?");
            args.add(region);
        }

        String sql;
        if ("new".equals(mode)) {
            where.add("(s.status IS NULL OR s.status='new')");
            sql = "SELECT q.qid FROM questions q LEFT JOIN srs s ON s.qid=q.qid WHERE "
                    + join(where) + " ORDER BY RANDOM() LIMIT ?";
        } else if ("review".equals(mode)) {
            where.add("s.due IS NOT NULL AND s.due<=? AND s.status<>'new'");
            args.add(today());
            sql = "SELECT q.qid FROM questions q JOIN srs s ON s.qid=q.qid WHERE "
                    + join(where) + " ORDER BY s.due LIMIT ?";
        } else if ("wrong".equals(mode)) {
            where.add("s.wrong_cnt>0");
            sql = "SELECT q.qid FROM questions q JOIN srs s ON s.qid=q.qid WHERE "
                    + join(where) + " ORDER BY s.wrong_cnt DESC, RANDOM() LIMIT ?";
        } else if ("fav".equals(mode)) {
            where.add("f.qid IS NOT NULL");
            sql = "SELECT q.qid FROM questions q JOIN favorites f ON f.qid=q.qid WHERE "
                    + join(where) + " ORDER BY RANDOM() LIMIT ?";
        } else {
            return new JSONObject();
        }
        args.add(String.valueOf(n));
        List<JSONObject> ids = rows(sql, args.toArray(new String[0]));
        JSONArray list = new JSONArray();
        for (JSONObject o : ids) {
            JSONObject full = question(o.optString("qid"));
            if (full != null) list.put(full);
        }
        try {
            return new JSONObject().put("list", list);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    private String join(List<String> parts) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < parts.size(); i++) {
            if (i > 0) sb.append(" AND ");
            sb.append(parts.get(i));
        }
        return sb.toString();
    }

    private JSONObject question(String qid) {
        if (qid == null || qid.isEmpty()) return null;
        JSONObject o = row(
                "SELECT q.*, s.status, s.due, s.interval, s.reps, s.wrong_cnt, s.right_cnt," +
                        " (SELECT 1 FROM favorites f WHERE f.qid=q.qid) fav," +
                        " (SELECT text FROM notes n WHERE n.qid=q.qid) note" +
                        " FROM questions q LEFT JOIN srs s ON s.qid=q.qid WHERE q.qid=?", qid);
        if (o == null) return null;
        try {
            String opts = o.optString("options", "[]");
            o.put("options", new JSONArray(opts));
        } catch (Exception ignored) {
        }
        return o;
    }

    // ---------- 题库浏览 ----------

    private JSONObject browse(Map<String, String> p) {
        int page = 1;
        try {
            page = Integer.parseInt(get(p, "page", "1"));
        } catch (Exception ignored) {
        }
        if (page < 1) page = 1;
        int size = 20;

        List<String> where = new ArrayList<String>();
        List<String> args = new ArrayList<String>();
        String[][] filters = {
                {"module", "q.module"}, {"category", "q.category"},
                {"year", "q.year"}, {"region", "q.region"}
        };
        for (String[] f : filters) {
            String v = get(p, f[0], "");
            if (!v.isEmpty()) {
                where.add(f[1] + "=?");
                args.add(v);
            }
        }
        String kw = get(p, "kw", "").trim();
        if (!kw.isEmpty()) {
            where.add("(q.stem LIKE ? OR q.analysis LIKE ?)");
            args.add("%" + kw + "%");
            args.add("%" + kw + "%");
        }
        String cond = where.isEmpty() ? "1=1" : join(where);

        long total = count("SELECT COUNT(*) n FROM questions q WHERE " + cond,
                args.toArray(new String[0]));

        List<String> a2 = new ArrayList<String>(args);
        a2.add(String.valueOf(size));
        a2.add(String.valueOf((page - 1) * size));
        List<JSONObject> list = rows(
                "SELECT q.qid,q.module,q.category,q.year,q.region,q.paper," +
                        " substr(replace(q.stem,'<p>',''),1,90) brief, s.status,s.due,s.interval,s.wrong_cnt," +
                        " (SELECT 1 FROM favorites f WHERE f.qid=q.qid) fav" +
                        " FROM questions q LEFT JOIN srs s ON s.qid=q.qid WHERE " + cond +
                        " ORDER BY q.year DESC, q.qid LIMIT ? OFFSET ?",
                a2.toArray(new String[0]));
        for (JSONObject o : list) {
            try {
                String b = o.optString("brief", "").replaceAll("<[^>]+>", "").trim();
                o.put("brief", b);
            } catch (Exception ignored) {
            }
        }
        try {
            return new JSONObject().put("total", total).put("page", page)
                    .put("size", size).put("list", new JSONArray(list.toString()));
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    private JSONObject facets() {
        List<String> mods = new ArrayList<String>();
        for (JSONObject o : rows("SELECT module FROM questions GROUP BY module ORDER BY COUNT(*) DESC"))
            mods.add(o.optString("module"));
        List<String> years = new ArrayList<String>();
        for (JSONObject o : rows("SELECT year FROM questions GROUP BY year ORDER BY year DESC"))
            years.add(o.optString("year"));
        List<String> regions = new ArrayList<String>();
        for (JSONObject o : rows("SELECT region FROM questions GROUP BY region ORDER BY COUNT(*) DESC"))
            regions.add(o.optString("region"));
        try {
            return new JSONObject()
                    .put("modules", new JSONArray(mods.toString()))
                    .put("categories", new JSONArray(rows(
                            "SELECT module,category,COUNT(*) n FROM questions GROUP BY module,category ORDER BY n DESC"
                    ).toString()))
                    .put("years", new JSONArray(years.toString()))
                    .put("regions", new JSONArray(regions.toString()))
                    .put("region_counts", new JSONArray(rows(
                            "SELECT region, COUNT(*) n FROM questions WHERE region<>'' GROUP BY region ORDER BY n DESC"
                    ).toString()));
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    // ---------- 判分与记忆 ----------

    private JSONObject grade(JSONObject body) {
        String qid = body.optString("qid");
        JSONArray pickedArr = body.optJSONArray("picked");
        StringBuilder sb = new StringBuilder();
        if (pickedArr != null) {
            List<String> ps = new ArrayList<String>();
            for (int i = 0; i < pickedArr.length(); i++) ps.add(pickedArr.optString(i));
            java.util.Collections.sort(ps);
            for (String x : ps) if (sb.indexOf(x) < 0) sb.append(x);
        }
        String picked = sb.toString();

        JSONObject q = row("SELECT answer FROM questions WHERE qid=?", qid);
        if (q == null) return err("no such question");
        String ans = q.optString("answer", "");
        String sorted = sortChars(ans);
        boolean right = sorted.equals(picked);

        int g = body.optInt("grade", 0);
        if (g < 1 || g > 4) g = right ? 3 : 1;

        JSONObject cur = row("SELECT * FROM srs WHERE qid=?", qid);
        double ease = cur == null ? 2.5 : cur.optDouble("ease", 2.5);
        int iv = cur == null ? 0 : cur.optInt("interval", 0);
        int reps = cur == null ? 0 : cur.optInt("reps", 0);
        int lapses = cur == null ? 0 : cur.optInt("lapses", 0);

        String status;
        if (g <= 1) {
            reps = 0;
            lapses += 1;
            iv = 1;
            ease = Math.max(1.3, ease - 0.25);
            status = "learning";
        } else {
            int qq = g == 2 ? 3 : (g == 3 ? 4 : 5);
            ease = Math.max(1.3, ease + (0.1 - (5 - qq) * (0.08 + (5 - qq) * 0.02)));
            reps += 1;
            if (reps == 1) iv = 1;
            else if (reps == 2) iv = 6;
            else iv = Math.max(1, (int) Math.round(iv * ease));
            if (g == 2) iv = Math.max(1, (int) Math.round(iv * 0.6));
            status = reps >= 2 ? "review" : "learning";
        }
        Calendar cal = Calendar.getInstance();
        cal.add(Calendar.DAY_OF_MONTH, iv);
        String due = df.format(cal.getTime());
        String ts = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(new Date());

        synchronized (writeLock) {
            SQLiteStatement up = db().compileStatement(
                    "UPDATE srs SET status=?,ease=?,interval=?,reps=?,lapses=?,due=?,last=?," +
                            "right_cnt=right_cnt+?,wrong_cnt=wrong_cnt+? WHERE qid=?");
            up.bindString(1, status);
            up.bindDouble(2, ease);
            up.bindLong(3, iv);
            up.bindLong(4, reps);
            up.bindLong(5, lapses);
            up.bindString(6, due);
            up.bindString(7, ts);
            up.bindLong(8, right ? 1 : 0);
            up.bindLong(9, right ? 0 : 1);
            up.bindString(10, qid);
            int changed = up.executeUpdateDelete();
            up.close();
            if (changed == 0) {
                SQLiteStatement ins = db().compileStatement(
                        "INSERT INTO srs(qid,status,ease,interval,reps,lapses,due,last,right_cnt,wrong_cnt)" +
                                " VALUES(?,?,?,?,?,?,?,?,?,?)");
                ins.bindString(1, qid);
                ins.bindString(2, status);
                ins.bindDouble(3, ease);
                ins.bindLong(4, iv);
                ins.bindLong(5, reps);
                ins.bindLong(6, lapses);
                ins.bindString(7, due);
                ins.bindString(8, ts);
                ins.bindLong(9, right ? 1 : 0);
                ins.bindLong(10, right ? 0 : 1);
                ins.executeInsert();
                ins.close();
            }
            SQLiteStatement rev = db().compileStatement(
                    "INSERT INTO reviews(qid,grade,right,ts) VALUES(?,?,?,?)");
            rev.bindString(1, qid);
            rev.bindLong(2, g);
            rev.bindLong(3, right ? 1 : 0);
            rev.bindString(4, ts);
            rev.executeInsert();
            rev.close();
        }
        try {
            return new JSONObject().put("ok", true).put("right", right).put("answer", ans)
                    .put("due", due).put("interval", iv).put("status", status);
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    private String sortChars(String s) {
        if (s == null) return "";
        char[] a = s.toCharArray();
        java.util.Arrays.sort(a);
        StringBuilder sb = new StringBuilder();
        for (char c : a) if (sb.indexOf(String.valueOf(c)) < 0) sb.append(c);
        return sb.toString();
    }

    private JSONObject fav(JSONObject body) {
        String qid = body.optString("qid");
        boolean on = body.optBoolean("on", false);
        synchronized (writeLock) {
            if (on) {
                db().execSQL("INSERT OR REPLACE INTO favorites(qid,added) VALUES(?,?)", new Object[]{qid, today()});
            } else {
                db().execSQL("DELETE FROM favorites WHERE qid=?", new Object[]{qid});
            }
        }
        return ok();
    }

    private JSONObject note(JSONObject body) {
        String qid = body.optString("qid");
        String text = body.optString("text", "").trim();
        synchronized (writeLock) {
            if (!text.isEmpty()) {
                db().execSQL("INSERT OR REPLACE INTO notes(qid,text,updated) VALUES(?,?,?)",
                        new Object[]{qid, text, today()});
            } else {
                db().execSQL("DELETE FROM notes WHERE qid=?", new Object[]{qid});
            }
        }
        return ok();
    }

    private JSONObject ok() {
        try {
            return new JSONObject().put("ok", true);
        } catch (Exception e) {
            return new JSONObject();
        }
    }

    /** 学习记录打成一段 JSON，换机或重装后灌回去。只带记录，不带题库。 */
    private JSONObject exportData() {
        JSONObject o = new JSONObject();
        try {
            o.put("app", "hongjuan");
            o.put("version", 1);
            o.put("exported", today());
            o.put("srs", new JSONArray(rows(
                    "SELECT qid,status,ease,interval,reps,lapses,due,last,right_cnt,wrong_cnt FROM srs")));
            o.put("reviews", new JSONArray(rows("SELECT qid,grade,right,ts FROM reviews")));
            o.put("favorites", new JSONArray(rows("SELECT qid,added FROM favorites")));
            o.put("notes", new JSONArray(rows("SELECT qid,text,updated FROM notes")));
        } catch (Exception e) {
            return err("导出失败：" + e);
        }
        return o;
    }

    /** 覆盖导入。四张表先清空再灌，避免和现有记录混成两套。 */
    private JSONObject importData(JSONObject body) {
        if (!"hongjuan".equals(body.optString("app")) || body.optInt("version", 0) != 1) {
            return err("请使用行测红卷导出的 version=1 进度文件");
        }
        int records = 0;
        for (String name : new String[]{"srs", "reviews", "favorites", "notes"}) {
            if (!body.has(name)) continue;
            JSONArray list = body.optJSONArray(name);
            if (list == null) return err("进度记录格式错误：" + name);
            records += list.length();
            for (int i = 0; i < list.length(); i++) {
                JSONObject item = list.optJSONObject(i);
                if (item == null || !(item.opt("qid") instanceof String)
                        || !item.optString("qid").matches("[0-9]+")) {
                    return err("进度记录格式错误：" + name);
                }
            }
        }
        if (records == 0) return err("这份 JSON 里没有可导入的记录");
        JSONArray srs = body.optJSONArray("srs");
        JSONArray rev = body.optJSONArray("reviews");
        JSONArray fav = body.optJSONArray("favorites");
        JSONArray nts = body.optJSONArray("notes");
        if (srs == null && rev == null && fav == null && nts == null) {
            return err("这份 JSON 里没有可导入的记录");
        }
        int n = 0;
        synchronized (writeLock) {
            SQLiteDatabase d = db();
            d.beginTransaction();
            try {
                d.delete("srs", null, null);
                d.delete("reviews", null, null);
                d.delete("favorites", null, null);
                d.delete("notes", null, null);
                if (srs != null) {
                    for (int i = 0; i < srs.length(); i++) {
                        JSONObject r = srs.optJSONObject(i);
                        if (r == null) continue;
                        d.execSQL("INSERT OR REPLACE INTO srs(qid,status,ease,interval,reps,lapses,due,last,right_cnt,wrong_cnt)" +
                                        " VALUES(?,?,?,?,?,?,?,?,?,?)",
                                new Object[]{r.optString("qid"), r.optString("status", "new"),
                                        r.optDouble("ease", 2.5), r.optInt("interval", 0),
                                        r.optInt("reps", 0), r.optInt("lapses", 0),
                                        r.optString("due", null), r.optString("last", null),
                                        r.optInt("right_cnt", 0), r.optInt("wrong_cnt", 0)});
                        n++;
                    }
                }
                if (rev != null) {
                    for (int i = 0; i < rev.length(); i++) {
                        JSONObject r = rev.optJSONObject(i);
                        if (r == null) continue;
                        d.execSQL("INSERT INTO reviews(qid,grade,right,ts) VALUES(?,?,?,?)",
                                new Object[]{r.optString("qid"), r.optInt("grade", 0),
                                        r.optInt("right", 0), r.optString("ts", "")});
                    }
                }
                if (fav != null) {
                    for (int i = 0; i < fav.length(); i++) {
                        JSONObject r = fav.optJSONObject(i);
                        if (r == null) continue;
                        d.execSQL("INSERT OR REPLACE INTO favorites(qid,added) VALUES(?,?)",
                                new Object[]{r.optString("qid"), r.optString("added", "")});
                    }
                }
                if (nts != null) {
                    for (int i = 0; i < nts.length(); i++) {
                        JSONObject r = nts.optJSONObject(i);
                        if (r == null) continue;
                        d.execSQL("INSERT OR REPLACE INTO notes(qid,text,updated) VALUES(?,?,?)",
                                new Object[]{r.optString("qid"), r.optString("text", ""),
                                        r.optString("updated", "")});
                    }
                }
                d.setTransactionSuccessful();
            } catch (Exception e) {
                return err("导入失败：" + e);
            } finally {
                d.endTransaction();
            }
        }
        try {
            return new JSONObject().put("ok", true).put("count", n);
        } catch (Exception e) {
            return ok();
        }
    }

    private JSONObject err(String m) {
        try {
            return new JSONObject().put("__error", m);
        } catch (Exception e) {
            return new JSONObject();
        }
    }

    // ---------- 统计 ----------

    private JSONObject stats() {
        String t = today();
        Calendar cal = Calendar.getInstance();
        cal.add(Calendar.DAY_OF_MONTH, -29);
        String from = df.format(cal.getTime());
        try {
            JSONObject d = new JSONObject();
            d.put("modules", new JSONArray(rows(
                    "SELECT q.module, COUNT(DISTINCT q.qid) total," +
                            " COUNT(DISTINCT CASE WHEN s.status IN ('learning','review') THEN q.qid END) done," +
                            " COUNT(DISTINCT CASE WHEN s.wrong_cnt>0 THEN q.qid END) wrong" +
                            " FROM questions q LEFT JOIN srs s ON s.qid=q.qid GROUP BY q.module ORDER BY total DESC"
            ).toString()));
            d.put("recent", new JSONArray(rows(
                    "SELECT substr(ts,1,10) d, COUNT(*) n, SUM(right) right_n FROM reviews" +
                            " WHERE substr(ts,1,10)>=? GROUP BY d ORDER BY d", from).toString()));
            d.put("weak", new JSONArray(rows(
                    "SELECT q.category, COUNT(*) n FROM srs s JOIN questions q ON q.qid=s.qid" +
                            " WHERE s.wrong_cnt>0 GROUP BY q.category ORDER BY n DESC LIMIT 8").toString()));
            d.put("total", count("SELECT COUNT(*) n FROM questions"));
            d.put("done_total", count("SELECT COUNT(*) n FROM reviews"));
            d.put("today", t);
            return d;
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }
}
