'use strict';

const app = document.getElementById('app');

// 题库里有极少数图缺失，别让它留个破图图标
document.addEventListener('error', e => {
  const t = e.target;
  if (t && t.tagName === 'IMG') t.style.display = 'none';
}, true);
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// 题干里的 **加粗** 转成标签，其余 HTML 原样保留
const rich = s => String(s || '').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');

// 装进 APK 时没有 HTTP 服务，改走同一套接口的本地桥；浏览器里还是走 /api/
function bridge() {
  return (typeof window !== 'undefined' && window.HJNative) ? window.HJNative : null;
}

async function api(path, body) {
  const b = bridge();
  if (b) {
    const raw = b.call(path, body === undefined ? '' : JSON.stringify(body));
    const data = JSON.parse(raw || '{}');
    if (data && data.__error) throw new Error(data.__error);
    return data;
  }
  const opt = body === undefined ? undefined : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  };
  const r = await fetch('/api/' + path, opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || ('HTTP ' + r.status));
  return data;
}

function fail(e) {
  app.innerHTML = '<div class="sheet"><div class="err">出错了：' + esc(e.message || e) +
    '</div><div class="acts"><button class="btn ghost" onclick="location.reload()">重来</button></div></div>';
}

// ---------- 答题会话 ----------
const S = { mode: 'new', list: [], i: 0, picked: new Set(), reveal: false, right: 0, wrong: 0 };
const MODE_NAME = { new: '练习新题', review: '到期复习', wrong: '错题重练', fav: '收藏重练' };

// 挑范围：科目、地区、题量
async function drawSetup() {
  app.innerHTML = '<div class="loading">准备中</div>';
  try {
    const [ov, fa] = await Promise.all([api('overview'), api('facets')]);
    const mods = ov.modules.map(m =>
      '<button class="btn ghost sm" data-m="' + esc(m.module) + '">' + esc(m.module) +
      '<span style="opacity:.55"> ' + m.total + '</span></button>').join('');
    const regs = (fa.region_counts || []).map(r =>
      '<option value="' + esc(r.region) + '">' + esc(r.region) + ' · ' + r.n + ' 题</option>').join('');
    app.innerHTML =
      '<div class="sheet"><span class="kicker">练 习</span><h2>挑范围</h2>' +
      '<p class="sub">科目、地区、题量，选完点开始</p>' +

      '<div class="rule dashed"></div><p class="sub">科目</p>' +
      '<div class="acts" id="pick-mod">' +
      '<button class="btn ghost sm on" data-m="">全部模块</button>' + mods + '</div>' +

      '<div class="rule dashed"></div><p class="sub">地区</p>' +
      '<div class="acts"><select id="pick-region" class="setup-sel">' +
      '<option value="">全部地区</option>' + regs + '</select></div>' +

      '<div class="rule dashed"></div><p class="sub">题量</p>' +
      '<div class="acts" id="pick-n">' +
      '<button class="btn ghost sm" data-n="10">10 题</button>' +
      '<button class="btn ghost sm on" data-n="20">20 题</button>' +
      '<button class="btn ghost sm" data-n="30">30 题</button></div>' +

      '<div class="rule"></div>' +
      '<div class="acts"><button class="btn" id="go">开始抽题</button>' +
      '<span class="sub" id="pick-sum" style="align-self:center"></span></div>' +
      '</div>';

    let module = '', region = '', n = 20;
    const sum = () => {
      document.getElementById('pick-sum').textContent =
        (module || '全部模块') + ' · ' + (region || '全部地区') + ' · ' + n + ' 题';
    };
    app.querySelectorAll('#pick-mod [data-m]').forEach(b => b.onclick = () => {
      app.querySelectorAll('#pick-mod [data-m]').forEach(x => x.classList.remove('on'));
      b.classList.add('on'); module = b.dataset.m; sum();
    });
    app.querySelectorAll('#pick-n [data-n]').forEach(b => b.onclick = () => {
      app.querySelectorAll('#pick-n [data-n]').forEach(x => x.classList.remove('on'));
      b.classList.add('on'); n = Number(b.dataset.n); sum();
    });
    document.getElementById('pick-region').onchange = e => { region = e.target.value; sum(); };
    document.getElementById('go').onclick = () => startStudy('new', module, n, region);
    sum();
  } catch (e) { fail(e); }
}

// 中途不想练了：丢掉这一轮的队列，回到挑范围。已作答的记录早入库了，不会丢。
function resetSession() {
  Object.assign(S, { list: [], i: 0, picked: new Set(), reveal: false, right: 0, wrong: 0 });
  drawSetup();
}

async function startStudy(mode, module, n, region) {
  app.innerHTML = '<div class="loading">取题中</div>';
  try {
    const qs = 'pick?mode=' + mode + '&n=' + (n || 20) +
      '&module=' + encodeURIComponent(module || '') +
      '&region=' + encodeURIComponent(region || '');
    const d = await api(qs);
    if (!d.list.length) {
      const tip = mode === 'review' ? '今天没有到期的题，先去做新题。'
        : mode === 'wrong' ? '还没有错题，做得不错。'
          : mode === 'fav' ? '收藏夹是空的。' : '这个范围里取不到题。';
      app.innerHTML = '<div class="sheet"><h2>' + MODE_NAME[mode] + '</h2><p class="sub">' + tip +
        '</p><div class="acts"><a class="btn ghost" href="#/">回今日</a></div></div>';
      return;
    }
    Object.assign(S, { mode, list: d.list, i: 0, picked: new Set(), reveal: false, right: 0, wrong: 0 });
    drawQuestion();
  } catch (e) { fail(e); }
}

function drawQuestion() {
  const q = S.list[S.i];
  const pct = Math.round(S.i / S.list.length * 100);
  const multi = (q.answer || '').length > 1;
  app.innerHTML =
    '<div class="bar-top" style="width:' + pct + '%"></div>' +
    '<div class="sheet">' +
    '<div class="qhead"><span class="qno">第 ' + (S.i + 1) + ' 题 / 共 ' + S.list.length + ' 题</span>' +
    '<span class="tags"><i>' + esc(q.module) + '</i><i>' + esc(q.category) + '</i>' +
    (q.year ? '<i>' + esc(q.year) + '</i>' : '') +
    (q.region ? '<i>' + esc(q.region) + '</i>' : '') +
    (q.n_papers > 1 ? '<i>收录 ' + q.n_papers + ' 卷</i>' : '') +
    (multi ? '<i>多选</i>' : '') + '</span></div>' +
    (q.material ? '<div class="mat"><div class="mh">给定材料</div>' + rich(q.material) + '</div>' : '') +
    '<div class="stem">' + rich(q.stem) + '</div>' +
    '<div class="opts">' + S.list[S.i].options.map(optHtml).join('') + '</div>' +
    '<div id="after"></div>' +
    '<div class="tools">' +
    '<button id="fav">' + (q.fav ? '已收藏' : '收藏') + '</button>' +
    '<button id="note">笔记</button>' +
    '<button id="skip">跳过</button>' +
    '<button id="reset">换范围</button>' +
    '</div>' +
    '<p class="sub keys">A–D 选项 · Enter 对答案 · 1–4 自评</p>' +
    '</div>';

  app.querySelectorAll('.opt').forEach(b => b.onclick = () => {
    if (S.reveal) return;
    const k = b.dataset.k;
    if (multi) { S.picked.has(k) ? S.picked.delete(k) : S.picked.add(k); }
    else { S.picked.clear(); S.picked.add(k); }
    app.querySelectorAll('.opt').forEach(x => x.classList.toggle('sel', S.picked.has(x.dataset.k)));
    paintAction();
  });
  document.getElementById('fav').onclick = toggleFav;
  document.getElementById('note').onclick = editNote;
  document.getElementById('skip').onclick = () => { S.i++; S.picked.clear(); S.reveal = false; S.i >= S.list.length ? drawDone() : drawQuestion(); };
  document.getElementById('reset').onclick = resetSession;
  paintAction();
}

// 图形题的选项常常只有一张图或干脆只有字母，只在有文字时补一列
function optHtml(o) {
  const txt = String(o.v || '').replace(/<[^>]+>/g, '').trim();
  const body = (txt && txt !== o.k) ? '<span>' + rich(o.v) + '</span>' : '';
  return '<button class="opt" data-k="' + o.k + '"><span class="k">' + o.k + '</span>' + body + '</button>';
}

// 未揭晓时底下是对答案按钮，揭晓后换成自评四档
function paintAction() {
  const box = document.getElementById('after');
  if (!S.reveal) {
    box.innerHTML = '<div class="acts"><button class="btn" id="check">对答案</button></div>';
    document.getElementById('check').onclick = check;
    return;
  }
  const q = S.list[S.i];
  const ans = q.answer || '';
  const ok = [...S.picked].sort().join('') === ans.split('').sort().join('');
  box.innerHTML =
    '<div class="verdict ' + (ok ? 'ok' : 'no') + '"><span class="stamp">' + (ok ? '答对' : '答错') + '</span>' +
    '<span>正确答案 ' + esc(ans.split('').join(' · ')) + '</span></div>' +
    '<div class="ana"><div class="ah">解析</div>' + (rich(q.analysis) || '<p class="sub">这题原库没有解析。</p>') + '</div>' +
    '<div class="grade"><p>这道题你现在记得多少？（决定它下次什么时候回来）</p>' +
    '<div class="grade-btns">' +
    '<button data-g="1">忘了<small>明天再来</small></button>' +
    '<button data-g="2">勉强<small>缩短间隔</small></button>' +
    '<button data-g="3">一般<small>正常拉长</small></button>' +
    '<button data-g="4">熟了<small>拉得更长</small></button>' +
    '</div></div>';
  box.querySelectorAll('[data-g]').forEach(b => b.onclick = () => grade(Number(b.dataset.g)));
  app.querySelectorAll('.opt').forEach(x => {
    const k = x.dataset.k;
    x.classList.remove('sel');
    if (ans.includes(k)) x.classList.add('right');
    else if (S.picked.has(k)) x.classList.add('wrong');
  });
}

function check() {
  if (!S.picked.size) { alert('先选一个选项'); return; }
  S.reveal = true;
  paintAction();
}

async function grade(g) {
  const q = S.list[S.i];
  try {
    const d = await api('grade', { qid: q.qid, picked: [...S.picked], grade: g });
    d.right ? S.right++ : S.wrong++;
  } catch (e) { fail(e); return; }
  S.i++; S.picked.clear(); S.reveal = false;
  S.i >= S.list.length ? drawDone() : drawQuestion();
}

function drawDone() {
  const t = S.right + S.wrong;
  app.innerHTML = '<div class="sheet"><h2>这一轮做完了</h2>' +
    '<p class="sub">' + MODE_NAME[S.mode] + ' · 共 ' + t + ' 题</p>' +
    '<div class="cells"><div><b>' + S.right + '</b><span>答对</span></div>' +
    '<div class="hot"><b>' + S.wrong + '</b><span>答错</span></div>' +
    '<div><b>' + (t ? Math.round(S.right / t * 100) : 0) + '</b><span>正确率 %</span></div>' +
    '<div><b>' + (t - S.right - S.wrong) + '</b><span>跳过</span></div></div>' +
    '<div class="acts"><a class="btn" href="#/">回今日</a>' +
    '<button class="btn ghost" id="again">再来一轮</button>' +
    (S.wrong ? '<button class="btn ghost" id="redo">只练错的</button>' : '') + '</div></div>';
  document.getElementById('again').onclick = () => { S.list = []; S.i = 0; drawSetup(); };
  const redo = document.getElementById('redo');
  if (redo) redo.onclick = () => { S.list = []; startStudy('wrong'); };
  if (S.mode !== 'new') S.list = [];
}

async function toggleFav() {
  const q = S.list[S.i];
  q.fav = q.fav ? 0 : 1;
  await api('fav', { qid: q.qid, on: q.fav });
  document.getElementById('fav').textContent = q.fav ? '已收藏' : '收藏';
}

async function editNote() {
  const q = S.list[S.i];
  const box = document.getElementById('after');
  const old = q.note || '';
  box.insertAdjacentHTML('beforeend',
    '<div class="grade"><p>写点自己的话，下次翻到这题会看到。</p>' +
    '<textarea id="nt" rows="3" style="width:100%;font:inherit;padding:8px;border:1px solid var(--line-2);background:#fff">' +
    esc(old) + '</textarea><div class="acts"><button class="btn sm" id="nsave">存下</button></div></div>');
  document.getElementById('nsave').onclick = async () => {
    q.note = document.getElementById('nt').value;
    await api('note', { qid: q.qid, text: q.note });
    box.querySelector('.grade').remove();
  };
}

// ---------- 首页 ----------
async function viewHome() {
  app.innerHTML = '<div class="loading">翻本子中</div>';
  try {
    const d = await api('overview');
    const acc = d.today_done ? Math.round(d.today_right / d.today_done * 100) : 0;
    const rows = d.modules.map(m => {
      const p = m.total ? Math.round(m.done / m.total * 100) : 0;
      return '<div class="mod-row"><span class="nm">' + esc(m.module) + '</span>' +
        '<span class="bar"><i style="width:' + p + '%"></i></span>' +
        '<span class="num">' + m.done + ' / ' + m.total + '</span></div>';
    }).join('');
    app.innerHTML =
      '<div class="sheet"><span class="kicker">今 日</span>' +
      '<div class="headline"><b>' + d.due + '</b><span>' +
      (d.due ? '道题今天到期，该还账了' : '今天没有到期的题，接着往下学') + '</span></div>' +
      '<div class="cells">' +
      '<div><b>' + d.today_done + '</b><span>今日已练</span></div>' +
      '<div><b>' + acc + '</b><span>今日正确率 %</span></div>' +
      '<div class="hot"><b>' + d.wrong + '</b><span>错题</span></div>' +
      '<div><b>' + d.streak + '</b><span>连续天数</span></div>' +
      '</div>' +
      '<div class="acts">' +
      '<button class="btn" id="go-study">开始练习</button>' +
      '<button class="btn ghost" id="go-review">复习到期</button>' +
      '<button class="btn ghost" id="go-wrong">重练错题</button>' +
      '</div>' +
      '<div class="rule"></div>' +
      '<p class="sub">全库 ' + d.total + ' 题，还剩 ' + d.new_left + ' 题没碰过。</p>' +
      '</div>' +
      '<div class="sheet"><h2>六科进度</h2><p class="sub">学过的算进去，学一半的也算</p>' +
      '<div class="mod-list">' + rows + '</div></div>';
    document.getElementById('go-study').onclick = () => { S.list = []; location.hash = '#/study'; };
    document.getElementById('go-review').onclick = () => { location.hash = '#/review'; };
    document.getElementById('go-wrong').onclick = () => { location.hash = '#/wrong'; };
  } catch (e) { fail(e); }
}

// ---------- 题库浏览 ----------
const F = { module: '', category: '', year: '', region: '', kw: '', page: 1 };

async function viewBrowse() {
  app.innerHTML = '<div class="loading">找题中</div>';
  try {
    const f = await api('facets');
    const opt = (arr, cur) => arr.map(v =>
      '<option value="' + esc(v) + '"' + (v === cur ? ' selected' : '') + '>' + esc(v) + '</option>').join('');
    const cats = f.categories.filter(c => !F.module || c.module === F.module);
    app.innerHTML =
      '<div class="sheet"><h2>题库</h2><p class="sub">按模块、年份、地区或关键词找题</p>' +
      '<div class="filters">' +
      '<select id="f-module"><option value="">全部模块</option>' + opt(f.modules, F.module) + '</select>' +
      '<select id="f-category"><option value="">全部考点</option>' + opt(cats.map(c => c.category), F.category) + '</select>' +
      '<select id="f-year"><option value="">全部年份</option>' + opt(f.years, F.year) + '</select>' +
      '<select id="f-region"><option value="">全部地区</option>' + opt(f.regions, F.region) + '</select>' +
      '<input id="f-kw" type="search" placeholder="关键词" value="' + esc(F.kw) + '">' +
      '<button class="btn sm" id="f-go">查</button>' +
      '</div><div id="list"></div></div>';
    const bind = id => document.getElementById(id);
    bind('f-module').onchange = e => { F.module = e.target.value; F.category = ''; F.page = 1; viewBrowse(); };
    bind('f-category').onchange = e => { F.category = e.target.value; F.page = 1; loadList(); };
    bind('f-year').onchange = e => { F.year = e.target.value; F.page = 1; loadList(); };
    bind('f-region').onchange = e => { F.region = e.target.value; F.page = 1; loadList(); };
    bind('f-go').onclick = () => { F.kw = bind('f-kw').value.trim(); F.page = 1; loadList(); };
    bind('f-kw').onkeydown = e => { if (e.key === 'Enter') bind('f-go').click(); };
    loadList();
  } catch (e) { fail(e); }
}

async function loadList() {
  const box = document.getElementById('list');
  if (!box) return;
  box.innerHTML = '<div class="loading">翻页中</div>';
  const qs = new URLSearchParams({ module: F.module, category: F.category, year: F.year, region: F.region, kw: F.kw, page: F.page });
  try {
    const d = await api('browse?' + qs);
    if (!d.list.length) { box.innerHTML = '<div class="empty">这个条件下没有题</div>'; return; }
    const rows = d.list.map(r =>
      '<button class="row" data-qid="' + esc(r.qid) + '"><div class="t">' + esc(r.brief) + '…</div>' +
      '<div class="m"><i>' + esc(r.module) + '</i><i>' + esc(r.category) + '</i><i>' + esc(r.year) + ' ' + esc(r.region) + '</i>' +
      (r.fav ? '<i class="flag">收藏</i>' : '') +
      (r.wrong_cnt ? '<i class="flag">错过 ' + r.wrong_cnt + '</i>' : '') +
      (r.status && r.status !== 'new' ? '<i>第 ' + (r.interval || 0) + ' 天间隔</i>' : '') +
      '</div></button>').join('');
    const pages = Math.max(1, Math.ceil(d.total / d.size));
    box.innerHTML = '<p class="sub">共 ' + d.total + ' 题</p>' + rows +
      '<div class="pager"><button class="btn sm ghost" id="pg-prev"' + (d.page <= 1 ? ' disabled' : '') + '>上一页</button>' +
      '<span>' + d.page + ' / ' + pages + '</span>' +
      '<button class="btn sm ghost" id="pg-next"' + (d.page >= pages ? ' disabled' : '') + '>下一页</button></div>';
    box.querySelectorAll('.row').forEach(b => b.onclick = () => { location.hash = '#/q/' + b.dataset.qid; });
    document.getElementById('pg-prev').onclick = () => { F.page--; loadList(); };
    document.getElementById('pg-next').onclick = () => { F.page++; loadList(); };
  } catch (e) { box.innerHTML = '<div class="err">' + esc(e.message) + '</div>'; }
}

// ---------- 单题 ----------
async function viewOne(qid) {
  app.innerHTML = '<div class="loading">打开</div>';
  try {
    const q = await api('question?qid=' + encodeURIComponent(qid));
    const opts = (q.options || []).map(o =>
      '<div class="opt' + (q.answer.includes(o.k) ? ' right' : '') + '"><span class="k">' + o.k + '</span><span>' + rich(o.v) + '</span></div>'
    ).join('');
    app.innerHTML =
      '<div class="sheet">' +
      '<div class="qhead"><span class="qno">' + esc(q.module) + ' · ' + esc(q.category) + '</span>' +
      '<span class="tags">' + (q.year ? '<i>' + esc(q.year) + '</i>' : '') +
      (q.region ? '<i>' + esc(q.region) + '</i>' : '') + '<i>qid ' + esc(q.qid) + '</i></span></div>' +
      (q.material ? '<div class="mat"><div class="mh">给定材料</div>' + rich(q.material) + '</div>' : '') +
      '<div class="stem">' + rich(q.stem) + '</div>' +
      '<div class="opts">' + opts + '</div>' +
      '<div class="ana"><div class="ah">答案 ' + esc(q.answer) + '</div>' + (rich(q.analysis) || '<p class="sub">原库无解析</p>') + '</div>' +
      (q.note ? '<div class="ana"><div class="ah">我的笔记</div><p>' + esc(q.note) + '</p></div>' : '') +
      '<div class="tools"><button id="fav">' + (q.fav ? '已收藏' : '收藏') + '</button>' +
      '<span class="sub" style="align-self:center">' + esc(q.paper) + '</span></div>' +
      '<div class="acts"><a class="btn ghost" href="#/browse">回题库</a></div></div>';
    document.getElementById('fav').onclick = async (e) => {
      q.fav = q.fav ? 0 : 1;
      await api('fav', { qid: q.qid, on: q.fav });
      e.target.textContent = q.fav ? '已收藏' : '收藏';
    };
  } catch (e) { fail(e); }
}

// ---------- 统计 ----------
async function viewStats() {
  app.innerHTML = '<div class="loading">算账中</div>';
  try {
    const d = await api('stats');
    const byDay = {};
    d.recent.forEach(r => { byDay[r.d] = r; });
    const days = [];
    for (let i = 29; i >= 0; i--) {
      const dt = new Date(Date.now() - i * 86400000);
      const k = dt.toISOString().slice(0, 10);
      days.push({ k, n: (byDay[k] || {}).n || 0 });
    }
    const max = Math.max(1, ...days.map(x => x.n));
    const bars = days.map(x => {
      const h = x.n ? 'height:' + Math.max(5, Math.round(x.n / max * 100)) + '%' : 'height:3px';
      return '<i data-z="' + (x.n ? 0 : 1) + '" style="' + h + '" title="' + x.k + '：做了 ' + x.n + ' 题"></i>';
    }).join('');
    const md = s => s.slice(5).replace('-', '/');
    const axis = '<div class="axis"><span>' + md(days[0].k) + '</span><span>' +
      md(days[14].k) + '</span><span>今天</span></div>';
    const mods = d.modules.map(m => '<tr><td>' + esc(m.module) + '</td>' +
      '<td class="num">' + m.total + '</td><td class="num">' + m.done + '</td>' +
      '<td class="num">' + (m.done ? Math.round(m.done / m.total * 100) : 0) + '%</td>' +
      '<td class="num">' + m.wrong + '</td></tr>').join('');
    const weak = d.weak.map(w => '<tr><td>' + esc(w.category) + '</td><td class="num">' + w.n + '</td></tr>').join('');
    app.innerHTML =
      '<div class="sheet"><h2>近三十天</h2><p class="sub">每天做了多少题</p>' +
      '<div class="chart">' + bars + '</div>' + axis +
      '<p class="sub" style="margin:2px 0 0">深色是有练过的日子</p></div>' +
      '<div class="sheet"><h2>各科</h2><table class="tbl"><tr><th>模块</th><th class="num">题量</th><th class="num">学过</th><th class="num">进度</th><th class="num">错题</th></tr>' +
      mods + '</table><div class="rule"></div>' +
      '<p class="sub">累计作答 ' + d.done_total + ' 次</p></div>' +
      (weak ? '<div class="sheet"><h2>错得最多的考点</h2><table class="tbl"><tr><th>考点</th><th class="num">错题数</th></tr>' + weak + '</table></div>'
        : '<div class="sheet"><h2>错得最多的考点</h2><div class="empty">还没有错题</div></div>');
  } catch (e) { fail(e); }
}

// ---------- 路由 ----------
function mark(k) {
  document.querySelectorAll('#tabs a').forEach(a => a.classList.toggle('on', a.dataset.k === k));
}

function route() {
  const h = (location.hash || '#/').replace(/^#/, '');
  window.scrollTo(0, 0);
  if (h === '/' || h === '') { mark('home'); return viewHome(); }
  if (h === '/study') {
    mark('study');
    return S.list.length && S.i < S.list.length ? drawQuestion() : drawSetup();
  }
  if (h === '/review') { mark('review'); S.list = []; return startStudy('review'); }
  if (h === '/wrong') { mark('wrong'); S.list = []; return startStudy('wrong'); }
  if (h === '/browse') { mark('browse'); return viewBrowse(); }
  if (h === '/stats') { mark('stats'); return viewStats(); }
  const m = h.match(/^\/q\/(\d+)$/);
  if (m) { mark('browse'); return viewOne(m[1]); }
  mark('home'); viewHome();
}

// 键盘：A-D 选，Enter 对答案，1-4 自评
document.addEventListener('keydown', e => {
  if (!S.list.length || !document.querySelector('.opt')) return;
  if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return;
  const k = e.key.toUpperCase();
  if (/^[A-E]$/.test(k)) {
    const btn = document.querySelector('.opt[data-k="' + k + '"]');
    if (btn) { btn.click(); e.preventDefault(); }
  } else if (e.key === 'Enter') {
    const c = document.getElementById('check');
    if (c) { c.click(); e.preventDefault(); }
  } else if (/^[1-4]$/.test(e.key)) {
    const g = document.querySelector('.grade-btns [data-g="' + e.key + '"]');
    if (g) { g.click(); e.preventDefault(); }
  }
});

// 点导航上的「练习」，永远回到挑范围，不再自动接着上一轮
document.querySelectorAll('#tabs a').forEach(a => {
  a.addEventListener('click', e => {
    if (a.dataset.k !== 'study' || !S.list.length) return;
    Object.assign(S, { list: [], i: 0, picked: new Set(), reveal: false, right: 0, wrong: 0 });
    if (location.hash === '#/study') { e.preventDefault(); mark('study'); drawSetup(); }
  });
});

window.addEventListener('hashchange', route);
route();
