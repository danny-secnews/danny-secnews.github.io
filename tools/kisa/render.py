#!/usr/bin/env python3
"""
KISA 보안공지 주간 리포트 렌더러 — 표준 라이브러리만 사용.

호별 데이터(content/kisa-cert/<week_start>.json)를 고정 틀(templates/kisa-cert/page.html)에 넣어
docs/kisa-cert/kisa_weekly_<week_start>_public.html 을 만든다. HTML은 이 결과와 정확히 같아야 한다.

  python tools/kisa/render.py 2026-09-28            한 호를 렌더링해 저장
  python tools/kisa/render.py --all                 content/kisa-cert/*.json 전부
  python tools/kisa/render.py 2026-09-28 --stdout   저장하지 않고 출력만

본문 글자 표기 (이것만 해석하고 나머지 글자는 모두 이스케이프)
  **굵게**   `코드`   [미확인](회색 표시)   줄바꿈(\n → <br>)

규칙
  - 날짜·제목·파일 이름은 데이터의 week_start, published_date로 코드가 만든다.
  - 출력은 UTF-8, 줄바꿈 LF로 고정(윈도·리눅스 같은 결과).
  - portal-date 메타와 상단 바 줄(build_manifest.NAV_TAG)을 넣어 build_manifest.py가 고칠 게 없게 한다.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import date as Day, timedelta
from pathlib import Path
from string import Template

REPO = Path(__file__).resolve().parents[2]
CONTENT = REPO / "content" / "kisa-cert"
OUT_DIR = REPO / "docs" / "kisa-cert"
TEMPLATE = REPO / "templates" / "kisa-cert" / "page.html"

sys.path.insert(0, str(REPO / "tools"))
from build_manifest import NAV_TAG  # noqa: E402  상단 바 줄은 한 곳에서만 정의

DOW = "월화수목금토일"
UNVERIFIED = "[미확인]"
MUTED = '<span style="color:#6B7280;">'
NOTE = '<span style="font-size:12px;color:#6B7280;">'
CODE = '<code style="word-break:break-all;">'
TOKEN = re.compile(r"(\*\*|`|\[미확인\]|\n)")

CELL = 'style="border:1px solid #D1D5DB;word-break:keep-all;"'
CELL_C = 'style="border:1px solid #D1D5DB;text-align:center;word-break:keep-all;"'
LABEL = 'valign="top" style="color:#6B7280;font-weight:700;word-break:keep-all;"'
P_LEAD = 'style="margin:0 0 11px;font-size:14.5px;line-height:1.78;color:#1F2937;word-break:keep-all;"'
P_LEAD_NOTE = 'style="margin:0 0 4px;font-size:13px;line-height:1.75;color:#6B7280;word-break:keep-all;"'
P_NOTE = 'style="margin:0 0 9px;font-size:13px;line-height:1.75;color:#1F2937;word-break:keep-all;"'
GRID = ('<div class="gw"><table role="presentation" class="grid" width="100%" cellpadding="6" '
        'cellspacing="0" style="border-collapse:collapse;font-size:{size}px;color:#1F2937;">')
TH = '<th style="border:1px solid #D1D5DB;text-align:left;">'


class RenderError(ValueError):
    pass


# ── 글자 ─────────────────────────────────────────────────────────

def esc(text: str) -> str:
    return html.escape(text, quote=False).replace(" ", "&nbsp;")


def inline(text: str, indent: str = "") -> str:
    """작은 표기법만 해석. 줄바꿈은 '<br>' + 줄바꿈 + indent."""
    if not isinstance(text, str):
        raise RenderError(f"글자가 아님: {text!r}")
    out: list[str] = []
    bold = code = False
    for tok in TOKEN.split(text):
        if not tok:
            continue
        if tok == "`":
            out.append("</code>" if code else CODE)
            code = not code
        elif code:
            if tok == "\n":
                raise RenderError(f"`코드` 안에 줄바꿈: {text!r}")
            out.append(esc(tok))
        elif tok == "**":
            out.append("</b>" if bold else "<b>")
            bold = not bold
        elif tok == UNVERIFIED:
            out.append(MUTED + UNVERIFIED + "</span>")
        elif tok == "\n":
            out.append("<br>\n" + indent)
        else:
            out.append(esc(tok))
    if bold or code:
        raise RenderError(f"닫히지 않은 {'**' if bold else '`'}: {text!r}")
    return "".join(out)


def lines(items: list, indent: str) -> str:
    """칸 안의 줄 목록. 각 줄은 글자 또는 {"note": 글자}(작은 회색 ※ 주석)."""
    parts = []
    for item in items:
        if isinstance(item, dict):
            parts.append(NOTE + inline(item["note"], indent) + "</span>")
        else:
            parts.append(inline(item, indent))
    return ("<br>\n" + indent).join(parts)


def severity(level: str) -> str:
    return '<b style="color:#9B1C1C;">긴급</b>' if level == "긴급" else f"<b>{esc(level)}</b>"


def muted(text: str) -> str:
    return MUTED + inline(text) + "</span>"


# ── 날짜 ─────────────────────────────────────────────────────────

def day(value: str, field: str) -> Day:
    try:
        return Day.fromisoformat(value)
    except (TypeError, ValueError):
        raise RenderError(f"{field} 날짜 형식 오류: {value!r}") from None


def dotted(d: Day, year: bool = True, dow: bool = True) -> str:
    s = (f"{d.year}." if year else "") + f"{d.month:02d}.{d.day:02d}"
    return s + (f"({DOW[d.weekday()]})" if dow else "")


def week_end(start: Day) -> Day:
    return start + timedelta(days=6)


def title_of(start: Day) -> str:
    end = week_end(start)
    return f"KISA 보호나라 보안공지 주간 리포트 ({dotted(start, dow=False)} ~ {dotted(end, end.year != start.year, False)})"


def out_name(week_start: str) -> str:
    return f"kisa_weekly_{week_start}_public.html"


# ── 구획 ─────────────────────────────────────────────────────────

def render_overview(data: dict) -> str:
    out = [f"  <p {P_LEAD}>\n    {inline(p, '    ')}\n  </p>" for p in data["overview"]]
    if data.get("overview_note"):
        out.append(f"  <p {P_LEAD_NOTE}>\n    {inline(data['overview_note'], '    ')}\n  </p>")
    return "\n".join(out)


def render_priority(rows: list[dict]) -> str:
    out = []
    for r in rows:
        target = f"<b>{inline(r['target'])}</b>" + (f"<br>{muted(r['target_note'])}" if r.get("target_note") else "")
        vuln = "<br>".join([inline(r["vuln"])] + [muted(x) for x in r.get("vuln_details", [])])
        risk = [severity(r["severity"]), muted(r["cvss"]), f"<b>{inline(r['exploitation'])}</b>"]
        risk += [muted(x) for x in r.get("exploitation_notes", [])]
        due = f"<b>{inline(r['deadline'])}</b>" + (f"<br>{muted(r['deadline_note'])}" if r.get("deadline_note") else "")
        out.append("    <tr>\n"
                   f"      <td {CELL}>{target}</td>\n"
                   f"      <td {CELL}>{vuln}</td>\n"
                   f"      <td {CELL_C}>{'<br>'.join(risk)}</td>\n"
                   f"      <td {CELL_C}>{due}</td>\n"
                   "    </tr>")
    return "\n".join(out)


KV_ROWS = (("situation", "상황", ""), ("remediation", "조치", ""), ("verification", "조치 적용 확인", ""),
           ("compromise_check", "침해 흔적 확인", ' style="background:#F3F6FA;"'))


def render_item(no: str, it: dict) -> str:
    ind = "      "
    rows = []
    for i, (key, label, tr) in enumerate(KV_ROWS):
        lbl = f'<td class="lbl" width="88" {LABEL}>' if i == 0 else f"<td {LABEL}>"
        rows.append(f"    <tr{tr}>{lbl}{label}</td><td style=\"word-break:keep-all;\">\n"
                    f"{ind}{lines(it[key], ind)}\n    </td></tr>")
    src = " · ".join(esc(s["label"]) for s in it["sources"])
    rows.append(f"    <tr><td {LABEL}>출처</td><td style=\"font-size:12px;color:#6B7280;word-break:break-word;\">\n"
                f"{ind}{src}\n    </td></tr>")
    meta = (f"{severity(it['severity'])} · {inline(it['meta'])}  <span style=\"color:#9CA3AF;\">|</span>  "
            f"{inline(it['meta_refs'])}")
    return ("<tr><td class=\"sec\" style=\"padding:10px 26px 4px;border-top:1px solid #E5E7EB;\">\n"
            f"  <h3 style=\"margin:0 0 3px;font-size:14.5px;color:#1F2937;\">{no}. {inline(it['title'])}</h3>\n"
            f"  <div style=\"font-size:12px;color:#6B7280;margin-bottom:9px;\">{meta}</div>\n"
            "  <table role=\"presentation\" class=\"kv\" width=\"100%\" cellpadding=\"6\" cellspacing=\"0\" "
            "style=\"font-size:13px;line-height:1.72;color:#1F2937;\">\n"
            + "\n".join(rows) + "\n  </table>\n</td></tr>\n")


def render_tracking(no: str, rows: list[dict]) -> str:
    if not rows:
        return ""
    body = []
    for r in rows:
        target = f"<b>{inline(r['target'])}</b>" + (f"<br>{muted(r['target_note'])}" if r.get("target_note") else "")
        body.append("    <tr>\n"
                    f"      <td {CELL}>{target}</td>\n"
                    f"      <td {CELL}>{inline(r['update'], '      ')}</td>\n"
                    "    </tr>")
    return ("<tr><td class=\"sec\" style=\"padding:10px 26px 4px;border-top:1px solid #E5E7EB;\">\n"
            f"  <h3 style=\"margin:0 0 3px;font-size:14.5px;color:#1F2937;\">{no}. 지난 호 수록분 — 조치 현황 추적</h3>\n"
            "  <div style=\"font-size:12px;color:#6B7280;margin-bottom:9px;\">신규 사실만 기재합니다. 상세 내용은 반복하지 않습니다.</div>\n"
            "  " + GRID.format(size="12.5") + "\n"
            "    <tr style=\"background:#F3F4F6;\">\n"
            f"      {TH}지난 호 항목</th>\n"
            f"      {TH}이번 주 확인된 신규 사실</th>\n"
            "    </tr>\n"
            + "\n".join(body) + "\n  </table></div>\n</td></tr>\n")


def render_audience(rows: list[dict]) -> str:
    out = []
    for r in rows:
        out.append("    <tr>\n"
                   f"      <td {CELL}><b>{inline(r['audience'])}</b></td>\n"
                   f"      <td {CELL}>\n      {inline(r['actions'], '      ')}</td>\n"
                   f"      <td {CELL_C}><b>{inline(r['deadline'])}</b></td>\n"
                   "    </tr>")
    return "\n".join(out)


def render_notes(blocks: list) -> str:
    out = []
    for b in blocks:
        if isinstance(b, dict):
            out.append("  <div style=\"background:#F8F9FA;border:1px solid #D1D5DB;padding:11px 13px;margin:0 0 9px;\">\n"
                       "    <p style=\"margin:0;font-size:13px;line-height:1.75;color:#1F2937;word-break:keep-all;\">\n"
                       f"      {inline(b['box'], '      ')}\n    </p>\n  </div>")
        else:
            out.append(f"  <p {P_NOTE}>\n    {inline(b, '    ')}\n  </p>")
    return "\n".join(out)


def render_unverified(data: dict) -> str:
    rows = data.get("unverified_table") or []
    if not rows:
        return ""
    body = []
    for r in rows:
        target = inline(r["target"]) + (f" {muted(r['target_note'])}" if r.get("target_note") else "")
        body.append(f"    <tr><td {CELL}>{target}</td><td {CELL}>{inline(r['content'])}</td>"
                    f"<td {CELL}>{inline(r['how'])}</td></tr>")
    out = ("\n\n  <p style=\"margin:12px 0 7px;font-size:13px;font-weight:700;color:#1F2937;\">남아 있는 [미확인] 항목</p>\n"
           "  " + GRID.format(size="12.3") + "\n"
           f"    <tr style=\"background:#F3F4F6;\">{TH}대상</th>{TH}내용</th>{TH}확인 경로</th></tr>\n"
           + "\n".join(body) + "\n  </table></div>")
    if data.get("unverified_footnote"):
        out += ("\n  <p style=\"margin:11px 0 0;font-size:12.5px;line-height:1.75;color:#6B7280;word-break:keep-all;\">\n"
                f"    {inline(data['unverified_footnote'], '    ')}\n  </p>")
    return out


# ── 전체 ─────────────────────────────────────────────────────────

def render(data: dict, source_path: str = "") -> str:
    """데이터 → HTML 문자열(LF). 같은 데이터는 언제나 같은 결과."""
    try:
        start = day(data["week_start"], "week_start")
        published = day(data["published_date"], "published_date")
        end = week_end(start)
        items = data["items"]
        page = TEMPLATE.read_text(encoding="utf-8").replace("\r\n", "\n")
        body = "".join(render_item(f"3-{i}", it) for i, it in enumerate(items, 1))
        return Template(page).substitute(
            title=esc(title_of(start)),
            published_date=published.isoformat(),
            source_path=esc(source_path or f"content/kisa-cert/{data['week_start']}.json"),
            nav_tag=NAV_TAG,
            preheader=inline(data["preheader"]),
            period=f"{dotted(start)} ~ {dotted(end, end.year != start.year)}",
            published_label=dotted(published),
            overview=render_overview(data),
            priority_rows=render_priority(data["priority"]),
            items=body,
            tracking=render_tracking(f"3-{len(items) + 1}", data.get("tracking") or []),
            audience_rows=render_audience(data["audience"]),
            notes=render_notes(data["notes"]),
            unverified=render_unverified(data),
            footer_sources=inline(data["footer_sources"], "    "),
        )
    except KeyError as e:
        raise RenderError(f"필수 칸 없음: {e.args[0]}") from None


def load(week_start: str) -> tuple[dict, Path]:
    path = CONTENT / f"{week_start}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f), path


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description="KISA 주간 리포트 데이터 → HTML")
    ap.add_argument("weeks", nargs="*", help="week_start (YYYY-MM-DD)")
    ap.add_argument("--all", action="store_true", help="content/kisa-cert/*.json 전부")
    ap.add_argument("--stdout", action="store_true", help="저장하지 않고 표준 출력으로")
    args = ap.parse_args()

    weeks = sorted(p.stem for p in CONTENT.glob("*.json")) if args.all else args.weeks
    if not weeks:
        ap.error("week_start 또는 --all 이 필요합니다")
    rc = 0
    for week in weeks:
        try:
            data, path = load(week)
            if data.get("week_start") != week:
                raise RenderError(f"파일 이름({week})과 week_start({data.get('week_start')})가 다름")
            text = render(data, path.relative_to(REPO).as_posix())
        except (OSError, json.JSONDecodeError, RenderError) as e:
            print(f"오류: {week}: {e}", file=sys.stderr)
            rc = 1
            continue
        if args.stdout:
            sys.stdout.flush()
            sys.stdout.buffer.write(text.encode("utf-8"))  # 윈도에서도 LF 그대로
            sys.stdout.buffer.flush()
        else:
            out = OUT_DIR / out_name(week)
            write(out, text)
            print(f"렌더링: {out.relative_to(REPO).as_posix()}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
