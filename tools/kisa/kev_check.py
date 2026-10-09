#!/usr/bin/env python3
"""
KISA 주간 리포트 KEV 대조 도구 — 호 데이터의 KEV 사실이 실제 CISA KEV 목록과 같은지 확인한다. 표준 라이브러리만 사용.
PR 검사(CI)에는 넣지 않는다 — KEV 목록은 매일 바뀌므로, 호에 적힌 판과 같은 목록으로만 비교한다.

  python tools/kisa/kev_check.py download --out <파일> [--source cisa|mirror]
  python tools/kisa/kev_check.py check <week_start> --catalog <파일> [--root DIR]

download  KEV 목록을 받아 <파일>로 저장한다(이미 있으면 덮어쓰지 않고 실패). 네트워크를 쓰는 것은 이 기능뿐이고
          아래 두 주소 밖으로는 접속하지 않는다. cisa가 막혀도 mirror로 저절로 넘어가지 않는다.
check     content/kisa-cert/<week_start>.json을 목록과 대조한다.
          새 호(구조화 칸): 판이 같아야 하고, 기록한 CVE의 KEV 상태·등재일·기한이 목록과 같아야 하며,
                           화면 글에만 나온 CVE가 목록에 있으면 실패. 줄여 쓴 CVE 번호가 있으면 실패.
                           대상 주간의 신규 등재 중 호에 없는 것은 안내.
          이전된 호: 판정하지 않고, 화면 글의 CVE(줄여 쓴 번호는 복원해 표시)마다 지금 받은 목록 기준의
                     등재 여부를 표로 보여 준다.

종료코드 (check) 0 일치(또는 이전된 호 안내) / 1 불일치 / 2 입력 오류(파일 없음·형식 오류·다른 판)
종료코드 (download) 0 저장 / 1 받기 실패·목록 형식 오류 / 2 입력 오류(이미 있는 파일 등)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date as Day, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCES = {
    "cisa": "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
    "mirror": "https://raw.githubusercontent.com/cisagov/kev-data/main/known_exploited_vulnerabilities.json",
}
STALE_DAYS = 7
CVE_ANY = re.compile(r"CVE-\d{4}-\d{4,}")
CVE_FULL = re.compile(r"^CVE-\d{4}-\d{4,}$")
CVE_YEAR = re.compile(r"CVE-(\d{4})-\d{4,}")
# 줄여 쓴 CVE 번호: 같은 글 안에서 온전한 CVE 뒤에 구분 기호(·, 쉼표, /)로 이어지는 4자리 이상 숫자.
# **굵게** 표시는 허용. 숫자 바로 뒤에 '-'·'.'·'/'나 영문·한글이 붙으면(버전·날짜·빌드·건수) 줄여 쓴 번호로 보지 않는다.
SHORT_LINK = re.compile(r"(?:\*\*)?\s*[·,/]\s*(?:\*\*)?(\d{4,})(?![0-9A-Za-z가-힣ㄱ-ㅎ_./-])")
YMD = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_DT = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})?$")
urlopen = urllib.request.urlopen  # 시험에서 바꿔 끼운다


class CatalogError(ValueError):
    pass


class InputError(ValueError):
    pass


@dataclass
class Catalog:
    version: str
    version_day: Day
    count: int
    released: datetime
    entries: dict[str, tuple[Day, Day]]   # CVE → (dateAdded, dueDate)


# ── 목록 파일 입력검사 ───────────────────────────────────────────

def _ymd(value, where: str) -> Day:
    if not isinstance(value, str) or not YMD.match(value):
        raise CatalogError(f"{where}: YYYY-MM-DD 날짜가 아님 ({value!r})")
    try:
        return Day.fromisoformat(value)
    except ValueError:
        raise CatalogError(f"{where}: 없는 날짜 ({value!r})") from None


def _iso_datetime(value, where: str) -> datetime:
    m = ISO_DT.match(value) if isinstance(value, str) else None
    if not m:
        raise CatalogError(f"{where}: ISO 8601 날짜·시각이 아님 ({value!r})")
    base, frac, tz = m.groups()
    text = base + (f".{(frac + '000000')[:6]}" if frac else "") + ("+00:00" if tz in (None, "Z") else tz)
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise CatalogError(f"{where}: 없는 날짜·시각 ({value!r})") from None


def parse_catalog(raw: bytes) -> Catalog:
    try:
        doc = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise CatalogError(f"JSON으로 읽을 수 없음: {e}") from None
    if not isinstance(doc, dict):
        raise CatalogError("목록 파일의 맨 바깥이 객체가 아님")
    version = doc.get("catalogVersion")
    if not isinstance(version, str) or not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", version):
        raise CatalogError(f"catalogVersion이 YYYY.MM.DD 형식이 아님 ({version!r})")
    try:
        version_day = datetime.strptime(version, "%Y.%m.%d").date()
    except ValueError:
        raise CatalogError(f"catalogVersion이 없는 날짜 ({version!r})") from None
    released = _iso_datetime(doc.get("dateReleased"), "dateReleased")
    count = doc.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise CatalogError(f"count가 0 이상의 정수가 아님 ({count!r})")
    vulns = doc.get("vulnerabilities")
    if not isinstance(vulns, list):
        raise CatalogError("vulnerabilities가 배열이 아님")
    if count != len(vulns):
        raise CatalogError(f"count({count})가 목록 길이({len(vulns)})와 다름")
    entries: dict[str, tuple[Day, Day]] = {}
    for n, v in enumerate(vulns, 1):
        where = f"vulnerabilities {n}번째"
        if not isinstance(v, dict):
            raise CatalogError(f"{where}: 객체가 아님")
        missing = [k for k in ("cveID", "dateAdded", "dueDate") if k not in v]
        if missing:
            raise CatalogError(f"{where}: 필수 칸 없음 {missing}")
        cve = v["cveID"]
        if not isinstance(cve, str) or not CVE_FULL.match(cve):
            raise CatalogError(f"{where}: cveID 형식 오류 ({cve!r})")
        if cve in entries:
            raise CatalogError(f"{where}: cveID 중복 ({cve})")
        entries[cve] = (_ymd(v["dateAdded"], f"{where} {cve} dateAdded"), _ymd(v["dueDate"], f"{where} {cve} dueDate"))
    return Catalog(version, version_day, count, released, entries)


# ── 화면 글 ──────────────────────────────────────────────────────
# "화면에 사람이 읽게 표시되는 글"의 범위. render.py가 화면에 넣는 칸과 같아야 한다.
# render.py·틀에 새 화면 칸이 생기면 이 함수도 함께 고친다(tools/kisa/README.md에도 적음).
# sources.url, 각종 id, checks, provenance, generated_at 같은 기계용 값은 넣지 않는다.
# 쪽 제목(<title>)은 날짜로 만들어지므로 데이터 칸이 아니다 — 여기서 "제목"은 항목 제목(items[].title)이다.

def _lines(values, where: str):
    for j, x in enumerate(values or []):
        if isinstance(x, dict):
            yield f"{where}[{j}].note", x.get("note")
        else:
            yield f"{where}[{j}]", x


def screen_texts(data: dict):
    """(위치, 글) 목록. 글이 아닌 값은 건너뛴다."""
    out = [("preheader", data.get("preheader"))]
    out += [(f"overview[{i}]", t) for i, t in enumerate(data.get("overview") or [])]
    out.append(("overview_note", data.get("overview_note")))
    for i, r in enumerate(data.get("priority") or []):  # 이전된 호의 2. 우선순위 표
        for k in ("target", "target_note", "vuln", "cvss", "exploitation", "deadline", "deadline_note"):
            out.append((f"priority[{i}].{k}", r.get(k)))
        out += [(f"priority[{i}].vuln_details[{j}]", t) for j, t in enumerate(r.get("vuln_details") or [])]
        out += [(f"priority[{i}].exploitation_notes[{j}]", t) for j, t in enumerate(r.get("exploitation_notes") or [])]
    for i, it in enumerate(data.get("items") or [], 1):
        w = f"3-{i}"
        for k in ("title", "meta", "meta_refs"):
            out.append((f"{w}.{k}", it.get(k)))
        p = it.get("priority") or {}  # 새 호의 표 한 줄 중 사람이 쓰는 부분
        for k in ("target", "deadline", "deadline_note"):
            out.append((f"{w}.priority.{k}", p.get(k)))
        out += [(f"{w}.priority.details[{j}]", t) for j, t in enumerate(p.get("details") or [])]
        for k in ("situation", "remediation", "verification", "compromise_check"):
            out += list(_lines(it.get(k), f"{w}.{k}"))
        out += [(f"{w}.sources[{j}].label", s.get("label")) for j, s in enumerate(it.get("sources") or [])]
    for i, r in enumerate(data.get("tracking") or []):
        for k in ("target", "target_note", "update"):
            out.append((f"tracking[{i}].{k}", r.get(k)))
    for i, r in enumerate(data.get("audience") or []):
        for k in ("audience", "actions", "deadline"):
            out.append((f"audience[{i}].{k}", r.get(k)))
    for i, b in enumerate(data.get("notes") or []):
        out.append((f"notes[{i}]", b.get("box") if isinstance(b, dict) else b))
    for i, r in enumerate(data.get("unverified_table") or []):
        for k in ("target", "target_note", "content", "how"):
            out.append((f"unverified_table[{i}].{k}", r.get(k)))
    out.append(("unverified_footnote", data.get("unverified_footnote")))
    out.append(("footer_sources", data.get("footer_sources")))
    for k, t in (data.get("boilerplate") or {}).items():
        out.append((f"boilerplate.{k}", t))
    return [(w, t) for w, t in out if isinstance(t, str)]


def text_cves(data: dict) -> dict[str, list[str]]:
    """화면 글에서 찾은 CVE → 나온 위치들."""
    found: dict[str, list[str]] = {}
    for where, text in screen_texts(data):
        for cve in CVE_ANY.findall(text):
            found.setdefault(cve, [])
            if where not in found[cve]:
                found[cve].append(where)
    return found


def abbreviations(text: str) -> list[tuple[str, str]]:
    """글 하나에서 줄여 쓴 CVE 번호 → [(복원한 CVE, 발견된 표기)]. 연도는 앞의 온전한 CVE의 연도를 붙인다."""
    out = []
    for m in CVE_YEAR.finditer(text):
        year, pos = m.group(1), m.end()
        while link := SHORT_LINK.match(text, pos):
            out.append((f"CVE-{year}-{link.group(1)}", text[m.start():link.end()]))
            pos = link.end()
    return out


def short_cves(data: dict) -> dict[str, list[tuple[str, str]]]:
    """화면 글에서 줄여 쓴 CVE(복원) → [(위치, 표기)]."""
    found: dict[str, list[tuple[str, str]]] = {}
    for where, text in screen_texts(data):
        for cve, shown in abbreviations(text):
            found.setdefault(cve, []).append((where, shown))
    return found


def recorded_vulns(data: dict) -> list[tuple[str, dict]]:
    """구조화 칸에 기록한 (항목, 취약점) — CVE가 있는 것만."""
    out = []
    for i, it in enumerate(data.get("items") or [], 1):
        for v in it.get("vulnerabilities") or []:
            if v["cve"]["state"] == "value":
                out.append((f"3-{i}", v))
    return out


def is_structured(data: dict) -> bool:
    return "checks" in data or any("vulnerabilities" in it for it in data.get("items") or [])


# ── 대조 ─────────────────────────────────────────────────────────

def _kev_desc(state: str, added=None, due=None) -> str:
    return f"KEV 등재 {added}, 기한 {due}" if state == "listed" else {"not_listed": "KEV 미등재"}.get(state, f"KEV {state}")


def check(data: dict, cat: Catalog) -> tuple[int, list[str]]:
    """(종료코드, 출력 줄들). 데이터는 validate.py를 통과한 모양이라고 보지만, 아니어도 예외 대신 입력 오류로 돌려준다."""
    try:
        return _check(data, cat)
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        return 2, [f"입력 오류: 호 데이터 모양이 예상과 다름({type(e).__name__}: {e}) — 먼저 validate.py를 통과시킬 것"]


def _check(data: dict, cat: Catalog) -> tuple[int, list[str]]:
    lines: list[str] = []
    start = Day.fromisoformat(data["week_start"])
    end = start + timedelta(days=6)
    lines.append(f"KEV 목록: 판 {cat.version} · {cat.count}건 · 배포 {cat.released.isoformat()}")
    lines.append(f"대상 주간: {start} ~ {end}")
    if cat.version_day < end:
        lines.append(f"⚠ 경고: 이 판({cat.version_day})은 대상 기간 끝({end})보다 이르다. "
                     "그 뒤의 등재는 이 대조로 확인되지 않는다.")
    in_text = text_cves(data)
    short = short_cves(data)
    period = sorted((c, a, d) for c, (a, d) in cat.entries.items() if start <= a <= end)

    if not is_structured(data):
        lines.append("")
        lines.append(f"이전된 호 — 판정하지 않음. 현재 받은 KEV 판({cat.version}) 기준 표"
                     "(그 호를 만들 당시의 목록이 아니라 지금 받은 목록에서 본 결과):")
        lines.append("  CVE | KEV 등재 여부 | 등재일 | 기한 | 화면에 나온 곳 | 줄여 쓴 번호(추정) 위치")
        for cve in sorted(set(in_text) | set(short)):
            hit = cat.entries.get(cve)
            places = in_text.get(cve, [])
            where = ", ".join(places[:3]) + (f" 외 {len(places) - 3}곳" if len(places) > 3 else "") if places else "-"
            shorts = ", ".join(f"{w} '{s}'" for w, s in short.get(cve, [])) or "-"
            lines.append(f"  {cve} | {'등재' if hit else '미등재'} | {hit[0] if hit else '-'} | {hit[1] if hit else '-'}"
                         f" | {where} | {shorts}")
        if not in_text and not short:
            lines.append("  (화면 글에 CVE 번호 없음)")
        lines += _period_info(period, set(in_text) | set(short))
        return 0, lines

    kev = (data.get("checks") or {}).get("kev")
    if not kev:
        return 2, lines + ["입력 오류: 호 데이터에 checks.kev(호 단위 KEV 확인 기록)가 없음"]
    if kev["catalog_version"] != cat.version or ("count" in kev and kev["count"] != cat.count):
        return 2, lines + [
            "입력 오류: 다른 판의 목록으로는 판정하지 않는다.",
            f"  호 데이터: 판 {kev['catalog_version']}" + (f" · {kev['count']}건" if "count" in kev else ""),
            f"  KEV 목록:  판 {cat.version} · {cat.count}건",
        ]

    bad: list[str] = []
    recorded = recorded_vulns(data)
    ids = {v["cve"]["id"] for _, v in recorded}
    for where, v in recorded:
        cve, k = v["cve"]["id"], v["kev"]
        hit = cat.entries.get(cve)
        mine = _kev_desc(k["state"], k.get("added"), k.get("due"))
        theirs = _kev_desc("listed", *hit) if hit else "KEV 미등재"
        same = (k["state"] == "listed" and hit and (Day.fromisoformat(k["added"]), Day.fromisoformat(k["due"])) == hit) \
            or (k["state"] == "not_listed" and not hit)
        if not same:
            bad += [f"  ✗ {where} {cve}", f"      호 데이터: {mine}", f"      KEV 목록:  {theirs}"]
    for cve in sorted(set(in_text) - ids):
        if cve in cat.entries:
            a, d = cat.entries[cve]
            bad += [f"  ✗ {cve}: 글에 나온 CVE가 KEV에 등재돼 있는데 구조화 칸에 없음",
                    f"      화면 글: {', '.join(in_text[cve])}",
                    f"      KEV 목록: {_kev_desc('listed', a, d)}"]
    if short:
        bad.append("  ✗ CVE 번호를 줄여 쓰지 않는다. 대조에서 빠질 수 있다 — 온전한 번호(CVE-YYYY-NNNN)로 적을 것:")
        for cve, uses in sorted(short.items()):
            bad += [f"      {where}: '{shown}' → {cve}" for where, shown in uses]

    lines.append("")
    lines.append(f"새 호 — 기록한 CVE {len(ids)}건, 화면 글의 CVE {len(in_text)}건을 판 {cat.version}과 대조")
    lines += ["불일치:"] + bad if bad else ["불일치 없음 — 호 데이터의 KEV 사실이 목록과 같다."]
    lines += _period_info(period, ids | set(in_text) | set(short))
    return (1 if bad else 0), lines


def _period_info(period, issue_cves: set[str]) -> list[str]:
    out = ["", f"대상 주간의 KEV 신규 등재 {len(period)}건:"]
    for cve, a, d in period:
        out.append(f"  {cve} | 등재 {a} | 기한 {d}" + ("" if cve in issue_cves else "  ← 이번 호에 없는 기간 내 KEV 신규 등재(안내)"))
    if not period:
        out.append("  (없음)")
    return out


# ── 목록 받기 ────────────────────────────────────────────────────

def download(out: Path, source: str, today: Day | None = None) -> int:
    today = today or datetime.now(timezone.utc).date()
    url = SOURCES[source]
    if out.exists():
        print(f"입력 오류: {out} 이(가) 이미 있음 — 덮어쓰지 않는다. 판마다 새 파일 이름을 쓴다(예: kev-YYYY.MM.DD.json).")
        return 2
    if not out.parent.is_dir():
        print(f"입력 오류: 저장할 폴더가 없음: {out.parent}")
        return 2
    print(f"받는 중: {source} — {url}")
    try:
        with urlopen(url, timeout=60) as r:  # 머리말을 꾸미지 않는다(브라우저인 척하지 않음)
            raw = r.read()
    except (urllib.error.URLError, OSError) as e:  # HTTPError(403 등)·접속 실패·시간 초과
        if isinstance(e, urllib.error.HTTPError):
            e.close()
        print(f"실패: {source}에서 받지 못함 — {e}")
        print(f"  브라우저에서 {url} 을 열어 저장한 파일을 check --catalog 로 넘기거나"
              + ("" if source == "mirror" else ", --source mirror 를 쓰라."))
        return 1
    try:
        cat = parse_catalog(raw)
    except CatalogError as e:
        print(f"실패: 받은 내용이 KEV 목록 형식이 아님 — {e} (파일을 남기지 않음)")
        return 1
    try:
        with open(out, "xb") as f:  # 그사이 같은 이름이 생겼어도 덮어쓰지 않는다
            f.write(raw)
    except FileExistsError:
        print(f"입력 오류: {out} 이(가) 이미 있음 — 덮어쓰지 않는다.")
        return 2
    age = (today - cat.version_day).days
    print(f"저장: {out}")
    print(f"  출처 {source} ({url})")
    print(f"  판 {cat.version} · {cat.count}건 · 배포 {cat.released.isoformat()} · 오늘({today}) 기준 {age}일 전 판")
    if age >= STALE_DAYS:
        print(f"  ⚠ 경고: {age}일 지난 판 — 최신이 아닐 수 있음")
    return 0


# ── 실행 ─────────────────────────────────────────────────────────

def run_check(week: str, catalog_path: Path, root: Path) -> tuple[int, list[str]]:
    try:
        cat = parse_catalog(catalog_path.read_bytes())
    except OSError as e:
        return 2, [f"입력 오류: 목록 파일을 읽을 수 없음 — {e}"]
    except CatalogError as e:
        return 2, [f"입력 오류: 목록 파일 형식 — {e}"]
    path = root / "content" / "kisa-cert" / f"{week}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        return 2, [f"입력 오류: 호 데이터를 읽을 수 없음 — {e}"]
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return 2, [f"입력 오류: 호 데이터가 JSON이 아님 — {e}"]
    if not isinstance(data, dict) or data.get("week_start") != week:
        return 2, [f"입력 오류: {path.name}의 week_start가 {week}가 아님"]
    return check(data, cat)


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description="KISA 주간 리포트 KEV 대조")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download", help="KEV 목록 받기")
    d.add_argument("--out", required=True)
    d.add_argument("--source", choices=sorted(SOURCES), default="cisa")
    c = sub.add_parser("check", help="호 데이터와 KEV 목록 대조")
    c.add_argument("week_start")
    c.add_argument("--catalog", required=True)
    c.add_argument("--root", default=str(REPO))
    args = ap.parse_args(argv)
    if args.cmd == "download":
        return download(Path(args.out), args.source)
    code, lines = run_check(args.week_start, Path(args.catalog), Path(args.root))
    print("\n".join(lines))
    legacy = any(line.startswith("이전된 호 —") for line in lines)
    print("결과: " + ("이전된 호 — 안내만(판정하지 않음)" if legacy and code == 0 else ["일치", "불일치", "입력 오류"][code]))
    return code


if __name__ == "__main__":
    sys.exit(main())
