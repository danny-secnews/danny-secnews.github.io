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
  - 고정 안내문은 표준 문구를 쓴다. 데이터의 boilerplate로 바꿔 쓰는 것은 이전된 호에만 허용(validate.py가 검사).
  - 항목 머리 줄: 구조화 칸(vulnerabilities·notices)이 있으면 그 값으로 만들고(새 호),
    없으면 meta·meta_refs 글자를 그대로 쓴다(이전된 호).
  - 데이터 형식 검사는 하지 않는다 — tools/kisa/validate.py 가 schema.json 으로 검사한다.
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
# 표준 고정 문구(09-28 기준). 새 호는 언제나 이 문구를 쓰고, 데이터의 boilerplate로 바꿔 쓰는 것은
# 이전된 호(validate.py의 면제 목록)에만 허용한다 — 과거 호의 원래 문구를 보존하기 위한 장치.
STANDARD_PRIORITY_FOOTNOTE = (
    "    ※ 권고 기한은 우선순위 예시입니다. 실제 일정은 자산 중요도·인터넷 노출 여부·변경관리 정책에 따라 조정하십시오.\n"
    "    악용 여부는 벤더 공지와 CISA KEV 등재를 근거로 하며 각 항목의 출처를 상세에 적었습니다.\n"
    "    KEV 기한은 미국 연방기관 기준으로, 사내 기한이 아니라 우선순위 참고값입니다.\n"
    "    악용 상태는 <b>악용 확인 / 보고 없음 / [미확인]</b> 세 가지만 사용합니다.")
STANDARD_FOOTER_NOTICE = (
    "    본 리포트는 보호나라 공지와 CISA 악용 확인 목록을 기준으로 조치·확인 방법을 보강한 참고자료입니다.\n"
    "    실제 적용 전 벤더 공식 문서와 각 조직의 변경관리 절차를 따르십시오.<br>\n"
    "    문의: KISA 사이버민원센터 국번없이 118")
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


# ── 구조화 머리 줄 (새 호) ─────────────────────────────────────────
# 항목에 vulnerabilities·notices가 있으면 머리 줄을 이 값들로 만든다. 문구는 여기서만 정한다.
#   위험도 · CVSS [· 벤더 등급] · 악용  |  KISA · [벤더 공지 ·] KEV
# 규칙의 검사는 validate.py의 check_new_issue()가 한다.

def md(d: Day, ref: Day) -> str:
    """M/D. 기준(발행일)과 연도가 다를 때만 연도를 붙인다."""
    return f"{d.month}/{d.day}" if d.year == ref.year else f"{d.year}/{d.month}/{d.day}"


def cvss_text(vulns: list[dict], total: int) -> str:
    scored = [v["cvss"] for v in vulns if v["cvss"]["state"] == "value"]
    if not scored:
        return f"CVSS {UNVERIFIED}"
    top = max(scored, key=lambda c: c["score"])  # 같은 점수면 앞의 것
    marks = [f"v{top['version']}"] if not top["version"].startswith("3.") else []
    marks += {"vendor": [], "nvd": ["NVD"], "cisa-adp": ["CISA-ADP"]}[top["basis"]]
    # "최대"는 전체를 모두 기록했고 모두 점수가 있을 때만 — 일부만 봤으면 전체의 최댓값이라 단정하지 않는다
    whole = total >= 2 and len(vulns) == total and len(scored) == total
    return f"CVSS {'최대 ' if whole else ''}{top['score']:.1f}" + (f"({', '.join(marks)})" if marks else "")


def exploitation_text(vulns: list[dict], total: int, published: Day) -> str:
    states = [v["exploitation"]["state"] for v in vulns]
    confirmed = states.count("confirmed")
    if confirmed and confirmed == total:
        return "악용 확인"
    if confirmed:
        return f"{confirmed}건 악용 확인"
    if all(s == "no_report" for s in states):
        as_of = md(min(day(v["exploitation"]["as_of"], "as_of") for v in vulns), published)
        # 일부만 기록했으면 기록한 범위를 밝힌다 — 기록하지 않은 CVE까지 보고 없음이라 단정하지 않는다
        return f"보고 없음({as_of} 기준)" if len(vulns) == total else f"보고 없음(기록 {len(vulns)}건 · {as_of} 기준)"
    return f"악용 {UNVERIFIED}"


def kev_text(vulns: list[dict], total: int, published: Day) -> str:
    listed = [(day(v["kev"]["added"], "kev.added"), day(v["kev"]["due"], "kev.due"))
              for v in vulns if v["kev"]["state"] == "listed"]
    if listed:
        if len(set(listed)) == 1:
            added, due = listed[0]
            return f"KEV 등재 {md(added, published)}(기한 {md(due, published)})"
        return f"KEV 등재 {len(listed)}건(가장 이른 기한 {md(min(d for _, d in listed), published)})"
    cves = {v["cve"]["state"] for v in vulns}
    if "unknown" in cves:  # CVE를 모르는 취약점이 하나라도 있으면 미등재라고 단정하지 않는다
        return f"KEV {UNVERIFIED}"
    if "value" not in cves:
        return "KEV 해당 없음"
    # KEV 확인 기록(complete)은 기록한 CVE만 조회했다는 뜻 — 일부만 기록했으면 그 범위를 밝힌다
    return "KEV 미등재" if len(vulns) == total else f"KEV 미등재(기록 {len(vulns)}건 기준)"


def structured_headline(it: dict, published: Day) -> tuple[str, str]:
    """구조화 칸 → (머리 줄 앞부분, 뒷부분). 본문 표기(rich) 글자로 돌려준다."""
    vulns = it["vulnerabilities"]
    total = it.get("cve_total", len(vulns))
    front = [cvss_text(vulns, total)]
    if it.get("vendor_rating"):
        r = it["vendor_rating"]
        front.append(f"벤더 등급 {r['label']}" + (f" {r['count']}건" if r.get("count") else ""))
    front.append(exploitation_text(vulns, total, published))

    kisa, vendor = it["notices"]["kisa"], it["notices"]["vendor"]
    if kisa["state"] == "value":
        extra = f", {it['addition']}" if it.get("addition") else ""
        back = [f"KISA #{kisa['no']}({md(day(kisa['posted'], 'kisa.posted'), published)} 게시{extra})"]
    elif kisa["state"] == "none_in_period":  # 확인한 대상 기간의 보호나라 게시판에 일치하는 공지가 없었다
        back = ["보호나라 대상 기간 공지 없음"]
    else:
        raise RenderError(f"notices.kisa.state를 알 수 없음: {kisa['state']!r}")
    dates = [day(a["date"], "vendor.date") for a in vendor.get("advisories", []) if a.get("date")]
    if vendor["state"] == "value" and dates:
        back.append(f"벤더 공지 {md(min(dates), published)}")
    back.append(kev_text(vulns, total, published))
    return " · ".join(front), " · ".join(back)


def render_item(no: str, it: dict, published: Day) -> str:
    ind = "      "
    rows = []
    for i, (key, label, tr) in enumerate(KV_ROWS):
        lbl = f'<td class="lbl" width="88" {LABEL}>' if i == 0 else f"<td {LABEL}>"
        rows.append(f"    <tr{tr}>{lbl}{label}</td><td style=\"word-break:keep-all;\">\n"
                    f"{ind}{lines(it[key], ind)}\n    </td></tr>")
    src = " · ".join(esc(s["label"]) for s in it["sources"])
    rows.append(f"    <tr><td {LABEL}>출처</td><td style=\"font-size:12px;color:#6B7280;word-break:break-word;\">\n"
                f"{ind}{src}\n    </td></tr>")
    if "vulnerabilities" in it:
        front, back = structured_headline(it, published)
    else:
        front, back = it["meta"], it["meta_refs"]
    meta = (f"{severity(it['severity'])} · {inline(front)}  <span style=\"color:#9CA3AF;\">|</span>  "
            f"{inline(back)}")
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
        body = "".join(render_item(f"3-{i}", it, published) for i, it in enumerate(items, 1))
        custom = data.get("boilerplate") or {}
        footnote = custom.get("priority_footnote")
        notice = custom.get("footer_notice")
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
            priority_footnote="    " + inline(footnote, "    ") if footnote else STANDARD_PRIORITY_FOOTNOTE,
            footer_notice="    " + inline(notice, "    ") if notice else STANDARD_FOOTER_NOTICE,
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
