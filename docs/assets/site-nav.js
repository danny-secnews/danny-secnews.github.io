/* 공통 상단 바 — 데일리·KISA 주간·법령·제도 분석 본문 페이지 맨 위에 붙는 바로가기.
   각 페이지 <head>에 아래 한 줄이 있으면 동작 (tools/build_manifest.py가 빠진 페이지에 자동으로 넣음)
     <script src="../assets/site-nav.js" defer data-site-nav></script>
   - Shadow DOM 안에 그려서 페이지 자체 CSS와 서로 간섭하지 않음 (본문 디자인은 그대로)
   - 페이지 배경이 어두우면 어두운 색, 인쇄할 때는 숨김
   - 이 바를 빼고 싶은 페이지: <head>에 <meta name="portal-nav" content="off">
   - 사이트 이름을 바꾸면 SITE_NAME도 같이 바꿀 것
   - 데일리 호(daily/YYYY-MM-DD.html, daily/)에는 발행일 이동 줄(‹ 이전 호 · 발행일 선택 · 다음 호 ›)을
     머리말 아래와 푸터 바로 위에 하나씩 붙임. 발행 목록은 data/archive.json(build.py가 매일 갱신)을
     열 때마다 읽으므로 지난 호 HTML은 다시 만들 필요 없음. 목록을 못 읽으면 이 줄만 빠짐 */
(function () {
  "use strict";

  var SITE_NAME = "보안정보 브리핑";
  var SECTIONS = [
    ["daily", "데일리"],
    ["kisa-cert", "KISA 주간"],
    ["law", "법령·제도 분석"]
  ];

  var me = document.currentScript;
  var body = document.body;
  if (!me || !body || !body.attachShadow || document.querySelector("site-nav-bar")) return;
  var off = document.querySelector('meta[name="portal-nav"]');
  if (off && /^\s*off\s*$/i.test(off.getAttribute("content") || "")) return;

  var root;
  try { root = new URL("../", me.src); } catch (e) { return; }  // assets/의 한 단계 위 = 사이트 루트
  var path = location.pathname;
  var rel = path.indexOf(root.pathname) === 0 ? path.slice(root.pathname.length) : "";  // 예: daily/2026-10-02.html
  var current = rel.split("/")[0];

  // 상단 바와 발행일 이동 줄이 함께 쓰는 글꼴·색
  var FONT = "400 14px/1.45 \"Pretendard\",\"Apple SD Gothic Neo\",\"Malgun Gothic\",\"맑은 고딕\"," +
    "\"Noto Sans KR\",\"Noto Sans CJK KR\",system-ui,sans-serif";
  var TONES =
    ".light{--ink:#1a1d23;--ink2:#3b414b;--rule:#cdd2d9;--accent:#1f4e8c}" +
    ".dark{--ink:#e6e8eb;--ink2:#c7ccd3;--rule:#353b45;--accent:#8fb3ec}";

  var css =
    ":host{display:block}" +
    "@media print{:host{display:none!important}}" +
    ".bar{font:" + FONT + ";color:var(--ink2);" +
    "border-bottom:1px solid var(--rule);-webkit-text-size-adjust:100%;text-size-adjust:100%;" +
    "word-break:keep-all;text-align:left;letter-spacing:normal}" +
    ".in{box-sizing:border-box;max-width:736px;margin:0 auto;display:flex;flex-wrap:wrap;" +
    "align-items:baseline;justify-content:space-between;gap:4px 16px;" +
    "padding:calc(10px + env(safe-area-inset-top,0px)) calc(20px + env(safe-area-inset-right,0px))" +
    " 10px calc(20px + env(safe-area-inset-left,0px))}" +
    "a{color:inherit;text-decoration:none}" +
    "a:hover{color:var(--ink);text-decoration:underline;text-underline-offset:3px}" +
    "a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}" +
    ".home{font-weight:700;color:var(--ink)}" +
    ".links{display:flex;flex-wrap:wrap;gap:4px 14px}" +
    ".links a{padding:2px 0;border-bottom:2px solid transparent}" +
    ".links a[aria-current=page]{color:var(--ink);font-weight:700;border-bottom-color:currentColor}" +
    TONES;

  var host = document.createElement("site-nav-bar");
  var shadow = host.attachShadow({ mode: "open" });
  var style = document.createElement("style");
  style.textContent = css;
  shadow.appendChild(style);

  var nav = document.createElement("nav");
  nav.setAttribute("aria-label", SITE_NAME + " 바로가기");
  var inner = document.createElement("div");
  inner.className = "in";
  var home = document.createElement("a");
  home.className = "home";
  home.href = root.href;
  home.textContent = SITE_NAME;
  var links = document.createElement("span");
  links.className = "links";
  SECTIONS.forEach(function (s) {
    var a = document.createElement("a");
    a.href = new URL(s[0] + "/", root).href;
    a.textContent = s[1];
    if (s[0] === current) a.setAttribute("aria-current", "page");
    links.appendChild(a);
  });
  inner.appendChild(home);
  inner.appendChild(links);
  nav.appendChild(inner);
  shadow.appendChild(nav);
  body.insertBefore(host, body.firstChild);

  // 페이지 배경 밝기에 맞춰 색 선택 (본문이 다크 모드를 지원하지 않으면 바도 밝게 유지)
  function luminance(color) {
    var m = /rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:[\s,\/]+([\d.]+)(%)?)?/.exec(color || "");
    if (!m) return null;
    var alpha = m[4] === undefined ? 1 : parseFloat(m[4]) / (m[5] ? 100 : 1);
    if (alpha < 0.5) return null;
    return (0.2126 * m[1] + 0.7152 * m[2] + 0.0722 * m[3]) / 255;
  }
  function isDark() {
    var els = [body, document.documentElement];
    for (var i = 0; i < els.length; i++) {
      var l = luminance(getComputedStyle(els[i]).backgroundColor);
      if (l !== null) return l < 0.45;
    }
    var cs = getComputedStyle(document.documentElement).colorScheme;
    var meta = document.querySelector('meta[name="color-scheme"]');
    var scheme = cs && cs !== "normal" ? cs : (meta && meta.getAttribute("content")) || "";
    return /dark/.test(scheme) && !!window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  var dateBars = [];  // 발행일 이동 줄(데일리 호에만 생김)도 상단 바와 같은 색으로 칠함
  function paint() {
    var tone = isDark() ? "dark" : "light";
    nav.className = "bar " + tone;
    dateBars.forEach(function (n) { n.className = "dn " + tone; });
  }
  paint();
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    if (mq.addEventListener) mq.addEventListener("change", paint);
    else if (mq.addListener) mq.addListener(paint);
  }

  // ── 데일리 호: 발행일 이동 줄 ──────────────────────────────────────────────
  //   ‹ 10. 1.(목)      [ 10. 2.(금) · 37건 ⌄ ]      10. 5.(월) ›
  // - 이전·다음은 archive.json에 있는 호끼리만 이어짐(발행 없는 날은 자연히 건너뜀), 끝에서는 '첫 호'·'최신 호'
  // - 목록을 기다리는 동안 위쪽 줄 자리를 잡아 둬서 본문이 밀리지 않게 하고, 못 읽으면 그 자리를 걷어 냄
  var DOW = ["일", "월", "화", "수", "목", "금", "토"];
  var DATE_CSS =
    ":host{display:block}" +
    ":host([data-pos=top]){margin:-6px 0 20px}" +
    ":host([data-pos=bottom]){margin:32px 0 0}" +
    "@media print{:host{display:none!important}}" +
    ".dn{font:" + FONT + ";color:var(--ink2);-webkit-text-size-adjust:100%;text-size-adjust:100%;" +
    "word-break:keep-all;text-align:left;letter-spacing:normal;min-height:36px;display:grid;" +
    // 양옆은 글자 폭 아래로 줄지 않고(줄바꿈 없음), 모자라면 가운데 목록이 줄어듦
    // (달 묶음 때문에 목록 칸에 20px쯤 여유가 있어 글자는 가려지지 않음)
    "grid-template-columns:minmax(max-content,1fr) auto minmax(max-content,1fr);align-items:center;gap:8px}" +
    ".light{--mute:#5f6670;color-scheme:light}.dark{--mute:#9ba3ad;color-scheme:dark}" +
    "a{color:inherit;text-decoration:none}" +
    "a:hover{color:var(--ink);text-decoration:underline;text-underline-offset:3px}" +
    "a:focus-visible,select:focus-visible{outline:2px solid var(--accent);outline-offset:2px}" +
    ".prev,.next{padding:6px 0;white-space:nowrap}" +
    ".prev{justify-self:start}" +
    ".next{justify-self:end;text-align:right}" +
    ".end{color:var(--mute)}" +
    ".pick{position:relative;display:flex;min-width:0}" +
    "select{font:inherit;font-weight:600;color:var(--ink);background:transparent;margin:0;" +
    "min-width:0;max-width:100%;border:1px solid var(--rule);border-radius:999px;" +
    "padding:5px 30px 5px 14px;cursor:pointer;-webkit-appearance:none;-moz-appearance:none;appearance:none}" +
    "select:hover{border-color:var(--ink2)}" +
    "option{font-weight:400}option,optgroup{color:CanvasText;background:Canvas}" +
    ".pick::after{content:\"\";position:absolute;top:50%;right:14px;width:5px;height:5px;margin-top:-4px;" +
    "border:solid var(--ink2);border-width:0 1.5px 1.5px 0;transform:rotate(45deg);pointer-events:none}" +
    "@media (pointer:coarse){select{font-size:16px}}" +  // iOS: 16px보다 작으면 고를 때 화면이 확대됨
    "@media (max-width:379px){.wd{display:none}}" +      // 폭 380px 미만 휴대폰: 이전·다음의 요일만 숨김(목록·aria-label엔 있음)
    "@media (max-width:349px){.dn{gap:6px}select{padding-left:11px;padding-right:25px}.pick::after{right:11px}}" +
    TONES;

  function day(s) {  // "2026-10-02" → {key, y, m, d, w}, 형식이 틀리거나 없는 날짜면 null
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || "");
    if (!m) return null;
    var t = new Date(Date.UTC(+m[1], m[2] - 1, +m[3]));  // UTC로 계산해 보는 사람 시간대와 무관하게 요일 고정
    if (t.getUTCMonth() !== m[2] - 1 || t.getUTCDate() !== +m[3]) return null;
    return { key: s, y: +m[1], m: +m[2], d: +m[3], w: DOW[t.getUTCDay()] };
  }
  function full(p) { return p.y + "년 " + p.m + "월 " + p.d + "일 (" + p.w + ")"; }  // build.py kdate()와 같은 꼴
  function pad(n) { return (+n < 10 ? "0" : "") + +n; }
  function issueUrl(key) { return new URL("daily/" + key + ".html", root).href; }
  function make(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text) n.textContent = text;
    return n;
  }
  function sideLink(dir, p) {  // dir: "prev"(이전 호, 왼쪽) | "next"(다음 호, 오른쪽)
    var a = make("a", dir);
    a.href = issueUrl(p.key);
    a.setAttribute("aria-label", (dir === "prev" ? "이전 호: " : "다음 호: ") + full(p));
    if (dir === "prev") a.appendChild(document.createTextNode("‹ "));
    a.appendChild(document.createTextNode(p.m + ". " + p.d + "."));
    a.appendChild(make("span", "wd", "(" + p.w + ")"));  // 좁은 화면에서는 숨김
    if (dir === "next") a.appendChild(document.createTextNode(" ›"));
    return a;
  }
  function picker(list, cur) {  // 전체 발행일, 최신 → 과거, 달마다 묶음
    var sel = make("select"), group = null, month = "";
    sel.setAttribute("aria-label", "발행일 선택");
    sel.setAttribute("autocomplete", "off");  // 뒤로 가기 때 브라우저가 고른 값을 되살리지 않게
    list.forEach(function (it) {
      var p = it.p, n = it.total;
      if (p.y + "-" + p.m !== month) {
        month = p.y + "-" + p.m;
        group = make("optgroup");
        group.label = p.y + "년 " + p.m + "월";
        sel.appendChild(group);
      }
      var o = make("option", "", p.m + ". " + p.d + ".(" + p.w + ")" +
        (typeof n === "number" && n >= 0 && n % 1 === 0 ? " · " + n + "건" : ""));
      o.value = p.key;
      group.appendChild(o);
    });
    sel.value = cur;
    return sel;
  }
  function shownDay() {  // daily/(최신호)가 실제로 보여 주는 호 — 제목의 'YYYY년 M월 D일'
    var re = /(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일/;
    var h1 = document.querySelector("h1");
    var m = re.exec(h1 ? h1.textContent : "") || re.exec(document.title);
    return m ? m[1] + "-" + pad(m[2]) + "-" + pad(m[3]) : "";
  }

  var issue = /^daily\/(?:(\d{4}-\d{2}-\d{2})(?:\.html)?|(?:index\.html)?)$/.exec(rel);
  if (!issue || !window.fetch || (issue[1] && !day(issue[1]))) return;  // 데일리 호가 아니면 여기까지

  function mount(pos, label, parent, before) {
    var h = document.createElement("site-date-nav");
    h.setAttribute("data-pos", pos);
    var sh = h.attachShadow({ mode: "open" });
    var st = document.createElement("style");
    st.textContent = DATE_CSS;
    var n = document.createElement("nav");
    n.setAttribute("aria-label", label);
    sh.appendChild(st);
    sh.appendChild(n);
    parent.insertBefore(h, before);
    dateBars.push(n);
    return h;
  }
  var head = document.querySelector("header.site");
  var foot = document.querySelector("footer.site");
  var spots = [
    mount("top", "발행일 이동", head ? head.parentNode : body, head ? head.nextSibling : host.nextSibling),
    mount("bottom", "발행일 이동(아래)", foot ? foot.parentNode : body, foot)
  ];
  paint();

  function fill(raw) {
    var seen = {}, list = [];
    (Array.isArray(raw) ? raw : []).forEach(function (a) {
      var p = day(a && a.date);
      if (p && !seen[p.key]) { seen[p.key] = true; list.push({ p: p, total: a.total }); }
    });
    if (!list.length) throw new Error("발행 목록이 비어 있음");
    function newestFirst(a, b) { return a.p.key < b.p.key ? 1 : a.p.key > b.p.key ? -1 : 0; }
    list.sort(newestFirst);

    var cur = issue[1] || shownDay();
    if (!day(cur)) cur = list[0].p.key;
    if (!seen[cur]) { list.push({ p: day(cur) }); list.sort(newestFirst); }  // 목록 갱신이 이 페이지보다 늦은 경우
    var at = 0;
    while (list[at].p.key !== cur) at++;
    var newer = at > 0 ? list[at - 1].p : null;
    var older = at + 1 < list.length ? list[at + 1].p : null;

    var leaving = false;
    function go(key) {
      if (!key || key === cur) return;
      leaving = true;
      location.href = issueUrl(key);
    }
    var selects = dateBars.map(function (n) {
      var sel = picker(list, cur), keyed = false;
      sel.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          if (sel.value !== cur) { e.preventDefault(); go(sel.value); }
          return;
        }
        // 닫힌 목록에서 화살표·글자 키로 값을 바꾸면 Windows 브라우저는 한 칸마다 change를 냄
        // → 이때는 바로 이동하지 않고 Enter를 기다림 (마우스·터치로 고르면 바로 이동)
        keyed = true;
        setTimeout(function () { keyed = false; }, 0);
      });
      sel.addEventListener("change", function () { if (!keyed) go(sel.value); });
      sel.addEventListener("blur", function () { if (!leaving) sel.value = cur; });  // 이동 없이 벗어나면 원래 날짜로
      var box = make("span", "pick");
      box.appendChild(sel);
      n.appendChild(older ? sideLink("prev", older) : make("span", "prev end", "첫 호"));
      n.appendChild(box);
      n.appendChild(newer ? sideLink("next", newer) : make("span", "next end", "최신 호"));
      return sel;
    });
    window.addEventListener("pageshow", function (e) {  // 뒤로 가기(bfcache)로 돌아오면 고른 값을 되돌림
      if (!e.persisted) return;
      leaving = false;
      selects.forEach(function (s) { s.value = cur; });
    });
  }

  fetch(new URL("data/archive.json", root).href, { cache: "no-cache" })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(fill)
    .catch(function (err) {
      spots.forEach(function (h) { if (h.parentNode) h.parentNode.removeChild(h); });
      dateBars.length = 0;
      if (window.console) console.warn("site-nav: 발행 목록(archive.json)을 읽지 못해 날짜 이동 줄을 생략", err);
    });
})();
