#!/usr/bin/env python3
"""
옛 HTML ↔ 새 HTML 비교 도구 — 게시본을 데이터로 옮긴 뒤 정보가 빠지지 않았는지 확인할 때 쓴다.
표준 라이브러리만 사용. 저장소 파일은 읽기만 한다.

  python tools/kisa/compare_html.py 옛.html 새.html
  python tools/kisa/compare_html.py git:origin/main:docs/kisa-cert/X.html docs/kisa-cert/X.html

비교 항목
  - 화면에 보이는 글자(블록 단위, 숨김 미리보기 문구 포함)와 제목
  - 토큰 개수: CVE 번호, 점이 들어간 숫자(버전 등), 모든 숫자, #번호, [미확인], URL
  - 문장 단위로 빠지거나 바뀐 것
  - 꾸밈(굵게·빨간 굵게·코드·회색·※주석·구분선) 위치와 개수
  - 태그 개수, 메타 태그 차이

종료코드 0 화면 글자·토큰·문장이 모두 같음(꾸밈 차이는 목록만 보여 줌) / 1 다름 / 2 파일을 못 읽음
"""
from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

BLOCK = {"p", "div", "tr", "td", "th", "h1", "h2", "h3", "table", "br", "body", "li"}
INLINE = ("b", "code", "span", "div", "i", "a")
TOKENS = {
    "CVE": r"CVE-\d{4}-\d+",
    "점이 들어간 숫자(버전 등)": r"\d+(?:\.\d+)+(?:-[\w.]+)?",
    "모든 숫자": r"\d+",
    "#번호": r"#\d+",
    "[미확인]": r"\[미확인\]",
    "URL": r"https?://[^\s\"'<>]+",
}


class Extract(HTMLParser):
    """화면 글자를 블록 단위로 모은다. rich=True면 꾸밈 표시(«굵게» 등)를 함께 남긴다."""

    def __init__(self, rich: bool):
        super().__init__(convert_charrefs=True)
        self.rich, self.blocks, self.cur, self.stack = rich, [], [], []
        self.skip = self.hidden = 0
        self.in_title, self.title = False, ""
        self.tags: Counter = Counter()
        self.metas: list[tuple] = []

    def flush(self) -> None:
        text = re.sub(r"[ \t\r\n]+", " ", "".join(self.cur)).strip(" ")
        if text:
            self.blocks.append(("[숨김] " if self.hidden else "") + text)
        self.cur = []

    def mark(self, tag: str, style: str) -> str:
        if not self.rich:
            return ""
        if tag == "b":
            return "«빨강굵게»" if "9B1C1C" in style else "«굵게»"
        if tag == "code":
            return "«코드»"
        if tag == "span" and "font-size:12px" in style:
            return "«주석»"
        if tag == "span" and "#6B7280" in style:
            return "«회색»"
        if tag == "span" and "#9CA3AF" in style:
            return "«구분»"
        if tag == "a":
            return "«링크»"
        return ""

    def handle_starttag(self, tag, attrs):
        style = (dict(attrs).get("style") or "").replace(" ", "")
        self.tags[tag] += 1
        if tag in ("style", "script"):
            self.skip += 1
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            self.metas.append(tuple(sorted((k, v or "") for k, v in attrs)))
        else:
            if tag in BLOCK:
                self.flush()
            if tag == "div" and "display:none" in style:
                self.hidden += 1
                self.stack.append("hidden")
                return
            m = self.mark(tag, style)
            if tag in INLINE:
                self.stack.append(m)
            self.cur.append(m)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self.skip -= 1
            return
        if tag == "title":
            self.in_title = False
            return
        if tag in INLINE and self.stack:
            m = self.stack.pop()
            if m == "hidden":
                self.flush()
                self.hidden -= 1
                return
            if m:
                self.cur.append(m.replace("«", "«/"))
        if tag in BLOCK:
            self.flush()

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_title:
            self.title += data
        else:
            self.cur.append(data)

    def handle_comment(self, data):
        self.tags["<!-- 주석 -->"] += 1


def load(spec: str) -> str:
    if spec.startswith("git:"):
        rev, _, path = spec[4:].partition(":")
        raw = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True, check=True).stdout
    else:
        raw = Path(spec).read_bytes()
    return raw.decode("utf-8").replace("\r\n", "\n")


def parse(doc: str, rich: bool) -> Extract:
    p = Extract(rich)
    p.feed(doc)
    p.close()
    p.flush()
    return p


def sentences(blocks: list[str]) -> list[str]:
    text = "\n".join(blocks).replace(" ", " ")
    return [s.strip() for s in re.split(r"(?<=[.다요음])\s+|\n", text) if s.strip()]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description="옛 HTML과 새 HTML의 화면 글자·토큰·문장·꾸밈 비교")
    ap.add_argument("old", help="옛 HTML 경로 또는 git:<커밋>:<경로>")
    ap.add_argument("new", help="새 HTML 경로 또는 git:<커밋>:<경로>")
    args = ap.parse_args()
    try:
        old, new = load(args.old), load(args.new)
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as e:
        print(f"읽기 실패: {e}")
        return 2

    po, pn = parse(old, False), parse(new, False)
    ro, rn = parse(old, True), parse(new, True)
    same = True

    print("== 파일")
    for name, doc in (("옛", old), ("새", new)):
        print(f"  {name}: {len(doc.encode())}바이트 {doc.count(chr(10))}줄")
    print("== 제목:", "같음" if po.title == pn.title else f"다름\n  옛 {po.title}\n  새 {pn.title}")
    same &= po.title == pn.title
    print("== 메타: 옛에만", sorted(set(po.metas) - set(pn.metas)), "/ 새에만", sorted(set(pn.metas) - set(po.metas)))

    print("\n== 화면 글자(블록 단위)")
    exact = po.blocks == pn.blocks
    flat = lambda b: re.sub(r"\s+", " ", " ".join(b).replace(" ", " "))
    print(f"  블록 수 {len(po.blocks)} / {len(pn.blocks)} | 완전 동일: {exact} | 공백·블록 경계 무시 동일: {flat(po.blocks) == flat(pn.blocks)}")
    same &= exact
    for line in difflib.unified_diff(po.blocks, pn.blocks, "옛", "새", n=0, lineterm=""):
        if not line.startswith(("---", "+++")):
            print("   ", line[:300])

    print("\n== 토큰 (옛 / 새)")
    fo, fn = flat(po.blocks), flat(pn.blocks)
    for name, pat in TOKENS.items():
        co, cn = Counter(re.findall(pat, fo)), Counter(re.findall(pat, fn))
        ok = co == cn
        same &= ok
        detail = "같음" if ok else f"다름 — 옛에만 {dict(co - cn)} / 새에만 {dict(cn - co)}"
        print(f"  {name}: {sum(co.values())} / {sum(cn.values())} (종류 {len(co)} / {len(cn)}) {detail}")

    print("\n== 문장 단위")
    so, sn = sentences(po.blocks), sentences(pn.blocks)
    d = [l for l in difflib.unified_diff(so, sn, n=0, lineterm="") if not l.startswith(("---", "+++", "@@"))]
    same &= not d
    print(f"  문장 수 {len(so)} / {len(sn)}, 빠지거나 바뀐 문장 {len(d)}건")
    for l in d:
        print("   ", l[:300])

    print("\n== 꾸밈 포함 비교 («굵게» «빨강굵게» «코드» «회색» «주석» «구분» «링크»)")
    diffs = [l for l in difflib.unified_diff(ro.blocks, rn.blocks, n=0, lineterm="") if not l.startswith(("---", "+++"))]
    print(f"  다른 블록 {sum(1 for l in diffs if l.startswith('-'))}개")
    for l in diffs:
        print("   ", l[:400])
    count = lambda p: Counter(m for b in p.blocks for m in re.findall(r"«[^/»]+»", b))
    mo, mn = count(ro), count(rn)
    for k in sorted(set(mo) | set(mn)):
        print(f"  {k}: {mo[k]} / {mn[k]}{'' if mo[k] == mn[k] else '   ← 다름'}")

    print("\n== 태그 개수 (옛 / 새)")
    for t in sorted(set(po.tags) | set(pn.tags)):
        a, b = po.tags[t], pn.tags[t]
        print(f"  {t}: {a} / {b}{'' if a == b else '   ← 다름'}")

    print("\n결과:", "화면 글자·토큰·문장 모두 같음" if same else "다름 — 위 목록 확인")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
