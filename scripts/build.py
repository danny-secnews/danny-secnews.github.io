"""수집 결과를 정적 사이트(HTML + RSS)로 렌더링."""
from __future__ import annotations

import html
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collect import KST, collect  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
E = html.escape


def fmt_time(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).astimezone(KST).strftime("%m/%d %H:%M")
    except Exception:  # noqa: BLE001
        return ""


def kdate(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    days = ["월", "화", "수", "목", "금", "토", "일"]
    return f"{dt.year}년 {dt.month}월 {dt.day}일 ({days[dt.weekday()]})"


def render_items(items: list[dict]) -> str:
    if not items:
        return '<p class="empty">신규 항목이 없습니다.</p>'
    rows = []
    for it in items:
        badges = []
        if it.get("highlight"):
            badges.append('<span class="badge hot">주요</span>')
        for cve in it.get("cves", []):
            badges.append(f'<span class="badge">{E(cve)}</span>')
        badge_html = f'<div class="badges">{"".join(badges)}</div>' if badges else ""
        desc = f'<p class="desc">{E(it["summary"])}</p>' if it.get("summary") else ""
        rows.append(
            f'<li class="{"hot" if it.get("highlight") else ""}">'
            f'<a class="t" href="{E(it["link"])}" target="_blank" rel="noopener noreferrer">{E(it["title"])}</a>'
            f'<div class="sub">{E(it["source"])} · {fmt_time(it.get("published"))}</div>'
            f"{desc}{badge_html}</li>"
        )
    return f'<ul class="items">{"".join(rows)}</ul>'


def render_body(data: dict, site: dict, page_url: str) -> str:
    hot = sum(1 for c in data["categories"] for i in c["items"] if i.get("highlight"))
    parts = [
        '<div class="summary">오늘 수집된 항목은 <strong>총 '
        f'{data["total"]}건</strong>이며, 이 중 주의가 필요한 주요 이슈는 '
        f"<strong>{hot}건</strong>입니다.</div>",
        f'<button class="share" onclick="copyLink(this)" data-url="{E(page_url)}">'
        "🔗 카카오톡 공유용 링크 복사</button>",
    ]
    for cat in data["categories"]:
        parts.append(
            f'<section class="cat"><h2>{cat["emoji"]} {E(cat["name"])} '
            f'<span class="count">{len(cat["items"])}</span></h2>'
            f'{render_items(cat["items"])}</section>'
        )
    return "\n".join(parts)


PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta property="og:type" content="article">
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta property="og:site_name" content="{site_title}">
<meta name="twitter:card" content="summary">
<link rel="canonical" href="{url}">
<link rel="alternate" type="application/rss+xml" title="{site_title}" href="{base}/rss.xml">
<link rel="stylesheet" href="{assets}/style.css">
</head>
<body>
<div class="wrap">
{nav}
<header class="site">
  <p class="brand">{site_title}</p>
  <h1>{heading}</h1>
  <p class="meta">{meta}</p>
</header>
{body}
{extra}
<footer class="site">
  <p>본 페이지는 공개된 RSS 피드를 수집해 매일 자동 생성됩니다. 각 항목의 제목을 누르면 원문으로 이동합니다.</p>
  <p>구독: <a href="{base}/rss.xml">RSS</a> · 정리 {author}</p>
</footer>
</div>
<script>
function copyLink(btn) {{
  var url = btn.getAttribute('data-url');
  var text = document.title + '\\n' + url;
  function done() {{ var o = btn.textContent; btn.textContent = '✅ 복사했습니다'; setTimeout(function(){{ btn.textContent = o; }}, 1800); }}
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(text).then(done, function(){{ window.prompt('아래 내용을 복사하세요', text); }});
  }} else {{ window.prompt('아래 내용을 복사하세요', text); }}
}}
</script>
</body>
</html>
"""


def write_page(path: str, **kw) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(PAGE.format(**kw))


def load_archive() -> list[dict]:
    path = os.path.join(DOCS, "data", "archive.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fp:
            return json.load(fp)
    return []


def build_rss(archive: list[dict], site: dict, base: str) -> None:
    now = datetime.now(KST)
    items = []
    for entry in archive[:40]:
        url = f'{base}/posts/{entry["date"]}.html'
        try:
            pub = datetime.strptime(entry["date"], "%Y-%m-%d").replace(hour=9, tzinfo=KST)
        except Exception:  # noqa: BLE001
            pub = now
        items.append(
            "<item>"
            f'<title>{E(site["title"])} — {E(kdate(entry["date"]))}</title>'
            f"<link>{E(url)}</link><guid isPermaLink=\"true\">{E(url)}</guid>"
            f'<description>{E(entry.get("headline", ""))}</description>'
            f"<pubDate>{format_datetime(pub)}</pubDate>"
            "</item>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        f'<title>{E(site["title"])}</title><link>{E(base)}/</link>'
        f'<description>{E(site["subtitle"])}</description>'
        "<language>ko</language>"
        f"<lastBuildDate>{format_datetime(now)}</lastBuildDate>"
        f'{"".join(items)}</channel></rss>'
    )
    with open(os.path.join(DOCS, "rss.xml"), "w", encoding="utf-8") as fp:
        fp.write(xml)


def main() -> int:
    # git does not track empty folders, so create output dirs every run.
    for sub in ("data", "posts", "assets"):
        os.makedirs(os.path.join(DOCS, sub), exist_ok=True)

    with open(os.path.join(ROOT, "feeds.json"), encoding="utf-8") as fp:
        config = json.load(fp)
    site = config["site"]
    base = site["base_url"].rstrip("/")
    # On GitHub Actions, derive base_url from the repository name.
    # A custom domain in feeds.json (no "github.io") is left untouched.
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if repo and "github.io" in base:
        owner, name = repo.split("/", 1)
        owner = owner.lower()
        if name.lower() == f"{owner}.github.io":
            base = f"https://{owner}.github.io"          # root site (no path)
        else:
            base = f"https://{owner}.github.io/{name}"   # project site
        print(f"    base_url 자동 설정: {base}")

    now = datetime.now(KST)
    if "--date" in sys.argv:
        now = datetime.strptime(sys.argv[sys.argv.index("--date") + 1], "%Y-%m-%d").replace(
            hour=9, tzinfo=KST
        )

    if "--mock" in sys.argv:
        with open(os.path.join(ROOT, "scripts", "mock.json"), encoding="utf-8") as fp:
            data = json.load(fp)
        data["date"] = now.strftime("%Y-%m-%d")
        data["generated_at"] = now.isoformat()
    else:
        print(f"[1/3] 피드 수집 ({now:%Y-%m-%d %H:%M} KST)")
        data = collect(config, now=now)

    date = data["date"]
    if data["total"] == 0 and "--allow-empty" not in sys.argv:
        print("[!] 수집 결과가 0건입니다. 페이지를 생성하지 않고 종료합니다.")
        return 0

    print(f"[2/3] 페이지 생성 (총 {data['total']}건)")
    with open(os.path.join(DOCS, "data", f"{date}.json"), "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)

    headline = ""
    for cat in data["categories"]:
        for item in cat["items"]:
            if item.get("highlight"):
                headline = item["title"]
                break
        if headline:
            break
    if not headline and data["categories"] and data["categories"][0]["items"]:
        headline = data["categories"][0]["items"][0]["title"]
    desc = f"{kdate(date)} · 총 {data['total']}건 · {headline}"[:180]

    post_url = f"{base}/posts/{date}.html"
    body = render_body(data, site, post_url)
    meta = f"{kdate(date)} · 자동 생성 {datetime.fromisoformat(data['generated_at']):%H:%M} KST"

    write_page(
        os.path.join(DOCS, "posts", f"{date}.html"),
        title=f"{site['title']} — {kdate(date)}",
        og_title=f"{site['title']} — {kdate(date)}",
        desc=desc, url=post_url, base=base, assets="../assets",
        site_title=site["title"], heading=kdate(date), meta=meta,
        nav=f'<p class="nav"><a href="../index.html">← 전체 목록</a></p>',
        body=body, extra="", author=site["author"],
    )

    archive = [a for a in load_archive() if a["date"] != date]
    archive.append({"date": date, "total": data["total"], "headline": headline})
    archive.sort(key=lambda a: a["date"], reverse=True)
    with open(os.path.join(DOCS, "data", "archive.json"), "w", encoding="utf-8") as fp:
        json.dump(archive, fp, ensure_ascii=False, indent=2)

    rows = "".join(
        f'<li><a href="posts/{a["date"]}.html">{kdate(a["date"])}</a>'
        f'<span class="n">{a["total"]}건</span></li>'
        for a in archive[1:31]
    )
    extra = f'<div class="archive"><h2>지난 발행</h2><ul>{rows}</ul></div>' if rows else ""

    write_page(
        os.path.join(DOCS, "index.html"),
        title=f"{site['title']} — {kdate(date)}",
        og_title=site["title"], desc=desc, url=f"{base}/", base=base, assets="assets",
        site_title=site["title"], heading=kdate(date), meta=meta, nav="",
        body=body, extra=extra, author=site["author"],
    )

    print("[3/3] RSS 생성")
    build_rss(archive, site, base)
    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    print(f"완료: {post_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
