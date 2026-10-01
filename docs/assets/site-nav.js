/* 공통 상단 바 — 데일리·KISA 주간·법령 분석 본문 페이지 맨 위에 붙는 바로가기.
   각 페이지 <head>에 아래 한 줄이 있으면 동작 (tools/build_manifest.py가 빠진 페이지에 자동으로 넣음)
     <script src="../assets/site-nav.js" defer data-site-nav></script>
   - Shadow DOM 안에 그려서 페이지 자체 CSS와 서로 간섭하지 않음 (본문 디자인은 그대로)
   - 페이지 배경이 어두우면 어두운 색, 인쇄할 때는 숨김
   - 이 바를 빼고 싶은 페이지: <head>에 <meta name="portal-nav" content="off">
   - 사이트 이름을 바꾸면 SITE_NAME도 같이 바꿀 것 */
(function () {
  "use strict";

  var SITE_NAME = "보안정보 브리핑";
  var SECTIONS = [
    ["daily", "데일리"],
    ["kisa-cert", "KISA 주간"],
    ["law", "법령 분석"]
  ];

  var me = document.currentScript;
  var body = document.body;
  if (!me || !body || !body.attachShadow || document.querySelector("site-nav-bar")) return;
  var off = document.querySelector('meta[name="portal-nav"]');
  if (off && /^\s*off\s*$/i.test(off.getAttribute("content") || "")) return;

  var root;
  try { root = new URL("../", me.src); } catch (e) { return; }  // assets/의 한 단계 위 = 사이트 루트
  var path = location.pathname;
  var current = path.indexOf(root.pathname) === 0 ? path.slice(root.pathname.length).split("/")[0] : "";

  var css =
    ":host{display:block}" +
    "@media print{:host{display:none!important}}" +
    ".bar{font:400 14px/1.45 \"Pretendard\",\"Apple SD Gothic Neo\",\"Malgun Gothic\",\"맑은 고딕\"," +
    "\"Noto Sans KR\",\"Noto Sans CJK KR\",system-ui,sans-serif;color:var(--ink2);" +
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
    ".light{--ink:#1a1d23;--ink2:#3b414b;--rule:#cdd2d9;--accent:#1f4e8c}" +
    ".dark{--ink:#e6e8eb;--ink2:#c7ccd3;--rule:#353b45;--accent:#8fb3ec}";

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
  function paint() { nav.className = "bar " + (isDark() ? "dark" : "light"); }
  paint();
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    if (mq.addEventListener) mq.addEventListener("change", paint);
    else if (mq.addListener) mq.addListener(paint);
  }
})();
