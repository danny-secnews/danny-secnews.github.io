#!/usr/bin/env python3
"""
포털 목록(docs/data/manifest.json) 생성기 — 표준 라이브러리만 사용.

docs/daily, docs/kisa-cert, docs/law 폴더의 *.html에서 제목·날짜·요약을 뽑아
하나의 JSON으로 묶는다. 포털(docs/index.html)과 목록 페이지가 이 파일을 읽는다.
같은 실행에서 본문 페이지에 공통 상단 바(assets/site-nav.js) 한 줄이 빠져 있으면 넣는다.

  python tools/build_manifest.py            바뀐 게 있을 때만 파일을 고쳐 씀
  python tools/build_manifest.py --check    고칠 게 있으면 종료코드 1 (파일은 그대로)
  python tools/build_manifest.py --no-nav   상단 바는 건드리지 않음

규칙
  - 날짜: <meta name="portal-date" content="YYYY-MM-DD">가 있으면 우선,
          없으면 파일 이름의 YYYY-MM-DD (법령·제도 분석은 '게시일'로 이름 붙이기 권장)
          KISA 주간은 메타가 없으면 본문 '대상 기간: … | 발행: YYYY.MM.DD' 줄의 발행일,
          그 줄을 못 읽거나 발행일이 대상 기간 시작일~31일 뒤 범위 밖이면 경고 후 파일 이름 날짜
  - 목록에서만 빼기: <head>에 <meta name="portal" content="hide">
  - 상단 바만 빼기:  <head>에 <meta name="portal-nav" content="off">
  - index.html, _로 시작하는 파일, 리다이렉트 안내 페이지는 목록에서 자동 제외

종료코드
  0 정상 / 1 --check에서 고칠 게 있음 / 2 docs/index.html이 포털이 아님
  2는 목록·상단 바 작업을 다 끝낸 뒤에 돌려준다. 데일리 워크플로에서는 이 단계를
  continue-on-error로 두고 맨 끝에서 결과를 확인하면, 데일리 발행은 막지 않고 알림만 받는다.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from collections import Counter
from datetime import date as Day, timedelta
from pathlib import Path
from urllib.parse import quote

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"
OUT = DOCS / "data" / "manifest.json"
CATEGORIES = ("daily", "kisa-cert", "law")  # 폴더 이름 = 구분 키 (portal.js, site-nav.js와 같아야 함)
NAV_TAG = '<script src="../assets/site-nav.js" defer data-site-nav></script>'
IN_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"

DATE_IN_NAME = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
META_TAG = re.compile(r"<meta\b[^>]*>", re.I)
ATTR = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""")
REFRESH = re.compile(r"""http-equiv\s*=\s*["']?refresh""", re.I)
PORTAL_LEVEL = re.compile(r"<html\b[^>]*\bdata-page\s*=", re.I)  # 포털·목록 페이지(자체 머리말 있음)
HEAD_END = re.compile(r"</head\s*>", re.I)
TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.I | re.S)
H1 = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.I | re.S)
SCRIPT_STYLE = re.compile(r"<(script|style)\b.*?</\1\s*>", re.I | re.S)
TAG = re.compile(r"<[^>]+>")
DAILY_PREFIX = re.compile(r"^오늘의\s*보안이슈\s*[—–|:\-]\s*")
# KISA 주간 머리말: '대상 기간: 2026.09.28(월) ~ 10.04(일) | 발행: 2026.10.05(월)' (태그·&nbsp; 걷어낸 뒤)
# 끝 날짜는 연도가 빠질 수 있어(12.28 ~ 01.03) 형태만 맞추고 값은 쓰지 않는다
KISA_ISSUE = re.compile(
    r"대상\s*기간\s*:\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?\s*(?:\([^)]*\))?"
    r"\s*~\s*(?:\d{4}\.\s*)?\d{1,2}\.\s*\d{1,2}\.?\s*(?:\([^)]*\))?"
    r"\s*\|\s*발행\s*:\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})")
KISA_MAX_LAG = timedelta(days=31)  # 발행일은 대상 기간 시작일부터 이 범위 안이어야 믿음


def note(level: str, msg: str) -> None:
    """Actions에서는 실행 요약에 보이는 주석으로, 로컬에서는 표준 오류로."""
    if IN_ACTIONS:
        print(f"::{level}::{msg}")
    else:
        print(("오류: " if level == "error" else "주의: ") + msg, file=sys.stderr)


def read(path: Path) -> str:
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        return f.read()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def plain(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", fragment))).strip()


def metas(doc: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for tag in META_TAG.findall(doc):
        attrs = {k.lower(): (dq or sq or bare) for k, dq, sq, bare in ATTR.findall(tag)}
        key = (attrs.get("name") or attrs.get("property") or "").lower()
        if key and "content" in attrs and key not in found:
            found[key] = html.unescape(attrs["content"]).strip()
    return found


def kisa_issue(doc: str) -> tuple[str, str, str]:
    """본문 머리말에서 (대상 기간 시작일, 발행일, 발행일을 못 쓰는 이유). 못 읽은 값은 ''."""
    m = KISA_ISSUE.search(plain(SCRIPT_STYLE.sub(" ", doc)))
    if not m:
        return "", "", "본문에 '대상 기간: … | 발행: …' 줄이 없음"
    y, mo, d, py, pm, pd = (int(g) for g in m.groups())
    try:
        start = Day(y, mo, d)
    except ValueError:
        return "", "", f"대상 기간 시작일이 없는 날짜: {y}.{mo:02d}.{d:02d}"
    try:
        published = Day(py, pm, pd)
    except ValueError:
        return start.isoformat(), "", f"발행일이 없는 날짜: {py}.{pm:02d}.{pd:02d}"
    if not timedelta(0) <= published - start <= KISA_MAX_LAG:
        return start.isoformat(), "", (f"발행일이 대상 기간 시작일부터 {KISA_MAX_LAG.days}일 안이 아님: "
                                       f"시작 {start}, 발행 {published}")
    return start.isoformat(), published.isoformat(), ""


def read_item(cat: str, path: Path, doc: str, warnings: list[str], weeks: dict[str, list[str]]) -> dict | None:
    if REFRESH.search(doc):
        return None  # 옮겨 간 자리의 안내 페이지
    meta = metas(doc)
    if meta.get("portal", "").lower() == "hide":
        return None

    m = TITLE.search(doc) or H1.search(doc)
    title = plain(m.group(1)) if m else ""
    if cat == "daily":
        title = DAILY_PREFIX.sub("", title)
    title = title or path.stem

    date = ""
    for key in ("portal-date", "article:published_time", "date"):
        value = meta.get(key, "")
        if ISO_DATE.match(value):
            date = value[:10]
            break
    found = DATE_IN_NAME.search(path.name)
    named = "-".join(found.groups()) if found else ""
    published = ""
    if cat == "kisa-cert":
        start, published, why = kisa_issue(doc)
        if start and named and start != named:
            warnings.append(f"KISA 대상 기간 시작일이 파일 이름 날짜와 다름: {cat}/{path.name} "
                            f"(본문 {start}, 파일 이름 {named})")
        if date:
            published = ""  # 메타 날짜(수동 보정)가 우선
        elif published:
            date = published
        else:
            warnings.append(f"KISA 발행일을 본문에서 못 읽어 파일 이름 날짜 사용: {cat}/{path.name} ({why})")
        # 같은 주차 중복 판단은 발행일이 아니라 대상 주간 기준
        week = start or named or date
        if week:
            weeks.setdefault(week, []).append(f"{cat}/{quote(path.name)}")
    if not date:
        date = named

    item: dict = {"cat": cat, "date": date, "title": title, "url": f"{cat}/{quote(path.name)}"}
    if cat == "kisa-cert" and not published:
        # kisa_weekly_2026-09-21_2026-09-27.html 처럼 날짜가 두 개면 대상 주간 끝 날짜로 씀
        # (date가 발행일이면 '발행일 ~ 끝 날짜'가 거꾸로 그려지므로 넣지 않음)
        found = ["-".join(g) for g in DATE_IN_NAME.findall(path.name)]
        if len(found) >= 2 and found[1] > date:
            item["until"] = found[1]
    desc = meta.get("description") or meta.get("og:description") or ""

    if cat == "daily":
        # 데일리 요약문: '2026년 10월 1일 (목) · 총 39건 · 대표 이슈 제목'
        parts = desc.split(" · ", 2)
        if len(parts) == 3:
            item["headline"] = parts[2].strip()
        body = plain(SCRIPT_STYLE.sub(" ", doc))
        total = re.search(r"총\s*(\d+)\s*건", body)
        major = re.search(r"주요\s*이슈는\s*(\d+)\s*건", body)
        if total:
            item["total"] = int(total.group(1))
        if major:
            item["major"] = int(major.group(1))
    elif desc:
        item["desc"] = desc
    return item


def scan() -> tuple[list[dict], list[tuple[Path, str]], list[str]]:
    """목록 항목, 상단 바를 넣을 (파일, 새 내용), 주의사항."""
    items: list[dict] = []
    nav_jobs: list[tuple[Path, str]] = []
    warnings: list[str] = []
    weeks: dict[str, list[str]] = {}  # KISA 대상 주간 시작일 → url
    for cat in CATEGORIES:
        folder = DOCS / cat
        if not folder.is_dir():
            warnings.append(f"{cat}/ 폴더가 없습니다")
            continue
        for path in sorted(folder.glob("*.html")):
            if path.name.startswith("_"):
                continue
            doc = read(path)

            if path.name != "index.html":
                item = read_item(cat, path, doc, warnings, weeks)
                if item is not None:
                    if not item["date"]:
                        warnings.append(f"날짜 없음: {item['url']} (파일 이름에 YYYY-MM-DD를 넣거나 portal-date 메타 추가)")
                    items.append(item)

            if "site-nav.js" in doc or REFRESH.search(doc) or PORTAL_LEVEL.search(doc):
                continue
            meta = metas(doc)
            if meta.get("portal", "").lower() == "hide" or meta.get("portal-nav", "").lower() == "off":
                continue
            m = HEAD_END.search(doc)
            if not m:
                warnings.append(f"</head>가 없어 상단 바를 넣지 못함: {cat}/{path.name}")
                continue
            nl = "\r\n" if "\r\n" in doc else "\n"
            nav_jobs.append((path, doc[:m.start()] + NAV_TAG + nl + doc[m.start():]))

    items.sort(key=lambda i: (i["date"], i["url"]), reverse=True)

    for week, urls in sorted(weeks.items(), reverse=True):
        if len(urls) > 1:
            warnings.append(f"KISA 같은 주차 {len(urls)}건({week}): " + ", ".join(sorted(urls, reverse=True)))

    posts = DOCS / "posts"
    if posts.is_dir():
        strays = [p.name for p in sorted(posts.glob("*.html")) if not REFRESH.search(read(p))]
        if strays:
            shown = ", ".join(strays[:5]) + (f" 외 {len(strays) - 5}건" if len(strays) > 5 else "")
            warnings.append(f"posts/에 안내 페이지가 아닌 파일 {len(strays)}건: {shown} — "
                            "아직 posts/로 저장하는 생성 경로가 있거나 분류 전 파일입니다")
    return items, nav_jobs, warnings


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    ap = argparse.ArgumentParser(description="포털 목록(docs/data/manifest.json) 생성 + 상단 바 보충")
    ap.add_argument("--check", action="store_true", help="고칠 게 있으면 종료코드 1, 파일은 건드리지 않음")
    ap.add_argument("--no-nav", action="store_true", help="본문 페이지에 상단 바를 넣지 않음")
    args = ap.parse_args()

    portal = DOCS / "index.html"
    portal_ok = portal.exists() and 'data-page="portal"' in read(portal)

    items, nav_jobs, warnings = scan()
    if args.no_nav:
        nav_jobs = []
    for w in warnings:
        note("warning", w)

    manifest = {"version": 1, "latest": items[0]["date"] if items else "", "items": items}
    new = json.dumps(manifest, ensure_ascii=False, indent=1) + "\n"
    old = read(OUT) if OUT.exists() else ""
    counts = Counter(i["cat"] for i in items)
    summary = ", ".join(f"{c} {counts.get(c, 0)}건" for c in CATEGORIES)

    rc = 0
    if args.check:
        todo = (["목록 갱신"] if new != old else []) + ([f"상단 바 {len(nav_jobs)}건"] if nav_jobs else [])
        print(("필요: " + ", ".join(todo) if todo else "변경 없음") + " — " + summary)
        rc = 1 if todo else 0
    else:
        if new != old:
            write(OUT, new)
            print("목록 갱신 —", summary)
        else:
            print("목록 변경 없음 —", summary)
        for path, text in nav_jobs:
            write(path, text)
        if nav_jobs:
            print(f"상단 바 추가 {len(nav_jobs)}건")

    if not portal_ok:
        note("error", "docs/index.html이 포털이 아닙니다 — 데일리 생성 코드가 아직 docs/index.html에 쓰고 "
                      "있는지 확인하세요(최신호 출력 경로는 docs/daily/index.html).")
        return 2
    return rc


if __name__ == "__main__":
    sys.exit(main())
