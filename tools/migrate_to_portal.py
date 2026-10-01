#!/usr/bin/env python3
"""
docs/posts/ 에 섞여 있는 발행물을 구분별 폴더로 옮기는 1회용 스크립트.

  python tools/migrate_to_portal.py --audit   영향도 분석만 출력 (경로·주소를 직접 쓰는 코드 목록)
  python tools/migrate_to_portal.py           계획 + 영향도 분석 출력 (아무것도 바꾸지 않음)
  python tools/migrate_to_portal.py --apply   실제로 옮김

하는 일
  1. 파일 이름으로 구분
       YYYY-MM-DD.html        -> docs/daily/
       kisa_weekly_*.html     -> docs/kisa-cert/
       YYYY-MM-DD-주제.html    -> docs/law/
     규칙에 안 맞는 파일(예: security-news-*)은 그대로 두고 따로 알려 줌
  2. 옮긴 파일 안의 /posts/파일명 주소(canonical, og:url 등)를 새 주소로 고침.
     데일리의 '← 전체 목록' 링크는 같은 폴더 index.html(최신호 + 지난 발행)로 연결
  3. 옛 자리(docs/posts/파일명)에는 새 주소로 넘겨 주는 안내 페이지를 남김.
     카톡·북마크로 이미 퍼진 링크가 깨지지 않게 하고, 링크 미리보기용 og 태그도 옮겨 적음
  4. docs/daily/index.html이 없으면 최신 데일리로 넘겨 주는 임시 페이지를 만듦
     (build.py 경로를 고친 뒤 첫 실행에서 진짜 최신호 페이지로 덮어써짐)

여러 번 실행해도 안전: 이미 안내 페이지로 바뀐 자리는 건너뜀.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"
POSTS = DOCS / "posts"
STUB_MARK = "<!-- moved-by-migrate_to_portal -->"
SITE_HOSTS = ("danny-secnews.github.io",)  # 이 주소의 /posts/ 링크만 고침 (외부 사이트 링크는 그대로)

# (구분 폴더, 파일 이름 규칙) — 위에서부터 먼저 맞는 규칙을 씀
RULES = [
    ("daily", re.compile(r"^\d{4}-\d{2}-\d{2}\.html$")),
    ("kisa-cert", re.compile(r"^kisa[_-]weekly.*\.html$", re.I)),
    ("law", re.compile(r"^\d{4}-\d{2}-\d{2}-.+\.html$")),
    ("law", re.compile(r"^incident-response-guide-.*\.html$", re.I)),
    ("daily", re.compile(r"^security-news-.*\.html$", re.I)),
    # 보류 파일의 구분을 정했다면 여기에 추가. 예:
    # ("daily", re.compile(r"^security-news-.*\.html$")),
]

POSTS_REF = re.compile(r"(https?://[^/\s\"'<>]+)?/posts/([^\s\"'<>?#]+)")
BACK_LINK = re.compile(
    r"""(<a\b[^>]*?\bhref\s*=\s*["'])[^"']*(["'][^>]*>\s*(?:<[^>]+>\s*)*"""
    r"""(?:←|&larr;|&#8592;|&#x2190;)\s*(?:<[^>]+>\s*)*전체\s*목록)""", re.I)
META_TAG = re.compile(r"<meta\b[^>]*>", re.I)
LINK_TAG = re.compile(r"<link\b[^>]*>", re.I)
ATTR = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""")
TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.I | re.S)
WEEK = re.compile(r"\d{4}-\d{2}-\d{2}")


def read(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def attrs_of(tag: str) -> dict[str, str]:
    return {k.lower(): (dq or sq or bare) for k, dq, sq, bare in ATTR.findall(tag)}


def classify(name: str) -> str | None:
    for cat, rule in RULES:
        if rule.match(name):
            return cat
    return None


def rewrite(text: str, cat: str, moved: dict[str, str]) -> str:
    def to_new(m: re.Match) -> str:
        host, name = m.group(1) or "", m.group(2)
        if name not in moved or (host and host.split("//", 1)[1].lower() not in SITE_HOSTS):
            return m.group(0)
        return f"{host}/{moved[name]}/{name}"

    text = POSTS_REF.sub(to_new, text)
    if cat == "daily":
        text = BACK_LINK.sub(r"\1./\2", text)
    return text


def stub(original: str, cat: str, name: str) -> str:
    rel = f"../{cat}/{quote(name)}"
    head = []
    found = TITLE.search(original)
    title = html.unescape(re.sub(r"\s+", " ", found.group(1)).strip()) if found else name

    seen = set()
    for tag in META_TAG.findall(original):
        a = attrs_of(tag)
        key = (a.get("name") or a.get("property") or "").lower()
        if key in ("description", "og:title", "og:description", "og:site_name", "og:type") and key not in seen:
            seen.add(key)
            kind = "property" if key.startswith("og:") else "name"
            head.append(f'<meta {kind}="{key}" content="{html.escape(html.unescape(a.get("content", "")))}">')

    old_url = ""
    for tag in META_TAG.findall(original) + LINK_TAG.findall(original):
        a = attrs_of(tag)
        if (a.get("property", "").lower() == "og:url" or a.get("rel", "").lower() == "canonical"):
            old_url = a.get("content") or a.get("href") or ""
            if old_url:
                break
    if f"/posts/{name}" in old_url:
        new_url = old_url.replace(f"/posts/{name}", f"/{cat}/{name}")
        head.append(f'<meta property="og:url" content="{html.escape(new_url)}">')
        head.append(f'<link rel="canonical" href="{html.escape(new_url)}">')

    return (
        "<!doctype html>\n<html lang=\"ko\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        f"{STUB_MARK}\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{html.escape(title)}</title>\n"
        + "".join(line + "\n" for line in head)
        + f"<meta http-equiv=\"refresh\" content=\"0; url={rel}\">\n"
        f"<script>location.replace({json.dumps(rel)} + location.search + location.hash);</script>\n"
        "</head>\n<body>\n"
        f"<p>주소가 바뀌었습니다. <a href=\"{rel}\">새 주소로 이동</a></p>\n"
        "</body>\n</html>\n"
    )


def daily_placeholder(latest: str) -> str:
    rel = quote(latest)
    return (
        "<!doctype html>\n<html lang=\"ko\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        f"{STUB_MARK}\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<title>오늘의 보안이슈</title>\n"
        f"<meta http-equiv=\"refresh\" content=\"0; url={rel}\">\n"
        "</head>\n<body>\n"
        f"<p><a href=\"{rel}\">최신호로 이동</a></p>\n"
        "</body>\n</html>\n"
    )


CODE_EXTS = {".py", ".yml", ".yaml", ".sh", ".bash", ".ps1", ".bat", ".cmd",
             ".js", ".mjs", ".cjs", ".ts", ".json", ".toml", ".cfg", ".ini"}
SKIP_ANYWHERE = {".git", ".venv", "venv", "node_modules", "__pycache__"}
CHECKS = [  # (표시, 패턴) — 개편으로 고쳐야 할 수 있는 경로·주소
    ("posts", re.compile(r"""["'/\\]posts\b""")),
    ("index.html", re.compile(r"index\.html")),
    ("rss.xml", re.compile(r"rss\.xml")),
    ("사이트 주소", re.compile(r"github\.io")),
]


def audit() -> dict[str, list[tuple[int, str, str]]]:
    """docs/·tools/ 밖의 코드·설정에서 경로·주소를 직접 쓰는 줄을 모은다."""
    found: dict[str, list[tuple[int, str, str]]] = {}
    for path in sorted(REPO.rglob("*")):
        rel = path.relative_to(REPO)
        if not path.is_file() or rel.parts[0] in ("docs", "tools") or SKIP_ANYWHERE & set(rel.parts):
            continue
        if path.suffix.lower() not in CODE_EXTS and path.name != "Makefile":
            continue
        try:
            if path.stat().st_size > 1_000_000:
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for no, line in enumerate(lines, 1):
            kinds = [label for label, rx in CHECKS if rx.search(line)]
            if kinds:
                found.setdefault(rel.as_posix(), []).append((no, ", ".join(kinds), line.strip()[:110]))
    return found


def print_audit() -> bool:
    """출력하고, 고쳐야 할 후보(posts·index.html)가 있으면 True."""
    found = audit()
    print("[영향도 분석 — 경로·주소를 직접 쓰는 코드 (docs/, tools/ 제외)]")
    if not found:
        print("  없음. 생성 코드가 저장소 밖(로컬 PC, Cowork 작업 등)에 있다면 그쪽 저장 경로를 직접 확인하세요.")
        return False
    risky = False
    for name, rows in found.items():
        print(f"  {name}")
        for no, kinds, text in rows[:30]:
            print(f"    {no:>4}: [{kinds}] {text}")
        if len(rows) > 30:
            print(f"          … 외 {len(rows) - 30}줄")
        risky = risky or any("posts" in k or "index.html" in k for _, k, _ in rows)
    if risky:
        print("  -> [posts]·[index.html] 줄은 이번 개편에서 고쳐야 할 후보입니다. 고치기 전에는 푸시하지 마세요.")
        print("     (최신호 출력은 docs/daily/index.html, 개별 호는 docs/daily/, 커밋 범위는 git add docs)")
    print("  -> 저장소 밖에서 만드는 산출물(KISA 주간 등)도 저장 위치를 docs/kisa-cert/ 등으로 바꿔야 합니다.")
    return risky


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    ap = argparse.ArgumentParser(description="docs/posts 파일을 daily / kisa-cert / law 로 분리")
    ap.add_argument("--apply", action="store_true", help="실제로 옮김 (없으면 계획만 출력)")
    ap.add_argument("--audit", action="store_true", help="영향도 분석만 출력")
    args = ap.parse_args()

    if args.audit:
        print_audit()
        return 0

    if not POSTS.is_dir():
        print("docs/posts 폴더가 없습니다. 이 파일이 저장소의 tools/ 안에 있는지 확인하세요.")
        return 1

    moves, unmatched, conflicts, done = [], [], [], 0
    for path in sorted(POSTS.glob("*.html")):
        try:
            text = read(path)
        except UnicodeDecodeError:
            unmatched.append(path.name + "  (UTF-8 아님)")
            continue
        if STUB_MARK in text:
            done += 1
            continue
        cat = classify(path.name)
        if cat is None:
            unmatched.append(path.name)
        elif (DOCS / cat / path.name).exists():
            conflicts.append(f"{path.name}  ({cat}/에 같은 이름이 이미 있음)")
        else:
            moves.append((path, cat, text))

    print("[옮길 파일]")
    for path, cat, _ in moves:
        print(f"  posts/{path.name}  ->  {cat}/{path.name}")
    if not moves:
        print("  없음")
    counts: dict[str, int] = {}
    for _, cat, _ in moves:
        counts[cat] = counts.get(cat, 0) + 1
    if counts:
        print("  합계: " + ", ".join(f"{c} {counts[c]}건" for c in ("daily", "kisa-cert", "law") if c in counts))

    if unmatched:
        print("\n[보류 — 규칙에 안 맞아 그대로 둠]")
        for n in unmatched:
            print(f"  posts/{n}")
        print("  구분을 정해 RULES에 한 줄 추가하거나 직접 옮기세요.")
    if conflicts:
        print("\n[건너뜀]")
        for n in conflicts:
            print(f"  posts/{n}")
    if done:
        print(f"\n[이미 옮겨진 자리 {done}건은 건너뜀]")

    weeks: dict[str, list[str]] = {}
    for path, cat, _ in moves:
        if cat == "kisa-cert":
            found = WEEK.search(path.name)
            weeks.setdefault(found.group(0) if found else "?", []).append(path.name)
    dups = {k: v for k, v in weeks.items() if len(v) > 1}
    if dups:
        print("\n[확인 필요 — 같은 주차 KISA 파일이 여러 개]")
        for week, names in dups.items():
            print(f"  {week}: " + ", ".join(names))
        print("  최종본만 남기고 나머지는 지우거나, 파일 <head>에")
        print('  <meta name="portal" content="hide"> 를 넣으면 포털 목록에서 빠집니다.')

    print()
    print_audit()

    if not args.apply:
        print("\n계획만 출력했습니다. 실제로 옮기려면 --apply 를 붙여 다시 실행하세요.")
        return 0

    moved = {path.name: cat for path, cat, _ in moves}
    for path, cat, text in moves:
        write(DOCS / cat / path.name, rewrite(text, cat, moved))
        write(path, stub(text, cat, path.name))

    daily_index = DOCS / "daily" / "index.html"
    dailies = sorted(p.name for p in (DOCS / "daily").glob("????-??-??.html")) if (DOCS / "daily").is_dir() else []
    if dailies and not daily_index.exists():
        write(daily_index, daily_placeholder(dailies[-1]))
        print(f"\ndaily/index.html 임시 페이지 생성 (-> {dailies[-1]})")

    print(f"\n완료: {len(moves)}건 이동, 옛 주소 안내 페이지 {len(moves)}건 생성.")
    print("다음: 생성 코드 경로 수정 -> python tools/build_manifest.py -> 로컬 확인 -> 한 커밋으로 푸시")
    return 0


if __name__ == "__main__":
    sys.exit(main())
