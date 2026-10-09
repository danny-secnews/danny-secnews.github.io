#!/usr/bin/env python3
"""
KISA 주간 리포트 검사기 (첫 판: 구조 검사 + 렌더 일치 검사) — 표준 라이브러리만 사용.

  python tools/kisa/validate.py                  content/kisa-cert/*.json 전부와 docs/kisa-cert/ 폴더 검사
  python tools/kisa/validate.py 2026-09-28       해당 호만 (폴더 검사는 함께 함)
  python tools/kisa/validate.py --root DIR       다른 작업 트리의 데이터·HTML을 검사(검사 코드·스키마·틀은 이 파일 쪽 것을 씀)

검사
  1. 형식: 필수 칸과 형식은 schema.json 한 곳에서만 정의하고 여기서는 그 파일을 읽어 검사한다.
  2. 정체성·날짜: 파일 이름 = week_start = id, week_start는 월요일, published_date는 대상 주간이 끝난 뒤 ~ 시작일+31일
  3. 이전된 호 면제: MIGRATED_WEEKS 고정 목록에 있는 주차만 '이전된 호'로 인정한다(provenance 표시만 믿지 않음).
     목록 밖 주차(새 호)는 새 호 규칙 check_new_issue()(구조화 칸·출처·확인 기록)를 통과해야 한다.
  4. 렌더 일치: HTML = 데이터를 틀에 넣어 다시 만든 결과 (줄바꿈 CRLF/LF 차이만 무시, 나머지는 바이트 단위)
  5. HTML 필수 요소: portal-date 메타, 상단 바 줄, 구획 제목
  6. 폴더: docs/kisa-cert/의 HTML은 레거시 목록에 있거나 데이터에서 만든 것이어야 한다(같은 주차 중복 금지)

새 호 규칙(구조화 칸): check_new_issue() — 3번에서 면제 목록 밖 주차마다 부른다.

종료코드 0 통과 / 1 실패
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date as Day, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

CODE =Path(__file__).resolve().parents[2]       # 검사 코드·스키마·틀이 있는 쪽
sys.path.insert(0, str(CODE / "tools" / "kisa"))
import render as R  # noqa: E402

SCHEMA = CODE / "tools" / "kisa" / "schema.json"
IN_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"

# ── 이전된 호 면제 목록 ──────────────────────────────────────────
# 기존 게시본을 옮겨 적은 호만 여기에 넣는다. 이 주차들에만 허용되는 것:
#   글자로 옮긴 항목 머리 줄(meta, meta_refs) · 비어 있는 출처 URL · 근거 없음 · 고정 문구 바꿔 쓰기(boilerplate)
# 09-14, 09-21은 실제로 옮길 때 추가한다. 새로 생성하는 주차는 절대 넣지 않는다.
# 이 파일(tools/)은 자동화 PR이 건드릴 수 없는 경로다(STEP 5에서 경로 검사로 강제).
MIGRATED_WEEKS = frozenset({"2026-09-28"})

# 데이터 없이 남아 있는 옛 HTML(손으로 올린 게시본과 안내 페이지). 데이터로 옮기면 여기서 뺀다.
LEGACY_HTML = frozenset({
    "kisa_weekly_2026-09-07_public.html",        # 안내 페이지 → _final
    "kisa_weekly_2026-09-07_public_final.html",  # 구형 디자인, 고정
    "kisa_weekly_2026-09-14_public.html",
    "kisa_weekly_2026-09-14_public_old.html",    # 안내 페이지
    "kisa_weekly_2026-09-21_public.html",
})

SECTIONS = ("1. 한눈에 보기", "2. 우선순위", "3. 공지별 조치 방법과 조치 확인 방법",
            "4. 대상별 이번 주 권고 조치", "5. 집계 기준과 참고 사항")


# ── 스키마 검사 (schema.json에 쓰인 키워드만 해석, 모르는 키워드는 검사기 오류) ──────────
ANNOTATIONS = {"$schema", "$id", "title", "description", "$defs"}
KEYWORDS = {"type", "required", "properties", "additionalProperties", "items", "minItems",
            "minLength", "pattern", "enum", "const", "oneOf", "$ref", "minimum", "maximum"}
TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "integer": int, "number": (int, float)}


class SchemaBug(Exception):
    pass


def _tag_match(value, alt: dict, root: dict) -> bool:
    """oneOf 형식 중 하나가 값의 구분 칸(const·enum으로 정해진 칸, 예: state)과 맞는지."""
    if "$ref" in alt:
        alt = root["$defs"][alt["$ref"][8:]]
    if not isinstance(value, dict):
        return False
    for key, sub in alt.get("properties", {}).items():
        if ("const" in sub and value.get(key) != sub["const"]) or ("enum" in sub and value.get(key) not in sub["enum"]):
            return False
    return True


def schema_errors(value, schema: dict, root: dict, path: str = "$") -> list[str]:
    unknown = set(schema) - KEYWORDS - ANNOTATIONS
    if unknown:
        raise SchemaBug(f"schema.json에 검사기가 모르는 키워드: {sorted(unknown)} ({path})")
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            raise SchemaBug(f"지원하지 않는 $ref: {ref}")
        beside = set(schema) - {"$ref"} - ANNOTATIONS
        if beside:  # $ref 자리의 다른 검사 규칙은 해석하지 않으므로 조용히 무시하지 말고 알린다
            raise SchemaBug(f"$ref 옆의 검사 키워드는 적용되지 않음: {sorted(beside)} ({path}) — $defs 쪽에 넣을 것")
        return schema_errors(value, root["$defs"][ref[8:]], root, path)
    errs: list[str] = []
    if "oneOf" in schema:  # 같은 자리의 다른 키워드(type·properties 등)도 이어서 검사한다
        results = [schema_errors(value, alt, root, path) for alt in schema["oneOf"]]
        matched = sum(not r for r in results)
        if matched != 1:
            errs.append(f"{path}: 허용된 형식 중 정확히 하나에 맞아야 함({matched}개 일치)")
            if not matched:  # 가장 가까운 형식(구분 칸 state 등이 맞는 형식 우선) 기준으로 무엇이 틀렸는지
                pairs = zip(schema["oneOf"], results)
                errs += min(pairs, key=lambda p: (not _tag_match(value, p[0], root), len(p[1])))[1]
    if "const" in schema and value != schema["const"]:
        errs.append(f"{path}: {schema['const']!r} 이어야 함")
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} 는 허용 값({', '.join(map(str, schema['enum']))})이 아님")
    t = schema.get("type")
    if t:
        if not isinstance(value, TYPES[t]) or (t in ("integer", "number") and isinstance(value, bool)):
            return errs + [f"{path}: {t} 이어야 함"]
    if t == "object":
        for key in schema.get("required", []):
            if key not in value:
                errs.append(f"{path}.{key}: 필수 칸 없음")
        props = schema.get("properties", {})
        for key, sub in value.items():
            if key in props:
                errs += schema_errors(sub, props[key], root, f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                errs.append(f"{path}.{key}: 정의되지 않은 칸")
    elif t == "array":
        if len(value) < schema.get("minItems", 0):
            errs.append(f"{path}: 최소 {schema['minItems']}개 필요")
        for i, sub in enumerate(value):
            errs += schema_errors(sub, schema.get("items", {}), root, f"{path}[{i}]")
    elif t == "string":
        if len(value) < schema.get("minLength", 0):
            errs.append(f"{path}: 비어 있으면 안 됨")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append(f"{path}: 형식 오류 {value!r}")
    elif t in ("integer", "number"):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(f"{path}: {schema['minimum']} 이상이어야 함 (지금 {value})")
        if "maximum" in schema and value > schema["maximum"]:
            errs.append(f"{path}: {schema['maximum']} 이하여야 함 (지금 {value})")
    return errs


# ── 호별 검사 ────────────────────────────────────────────────────

def lf(raw: bytes) -> str:
    return raw.decode("utf-8").replace("\r\n", "\n")


def check_issue(root: Path, path: Path, schema: dict) -> list[str]:
    rel = path.relative_to(root).as_posix()
    try:
        data = json.loads(lf(path.read_bytes()))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return [f"JSON을 읽을 수 없음: {e}"]

    errs = schema_errors(data, schema, schema)
    if errs:
        return errs  # 형식이 틀리면 뒤 검사는 의미가 없음

    week = data["week_start"]
    if path.stem != week:
        errs.append(f"파일 이름({path.stem})과 week_start({week})가 다름")
    if data["id"] != f"kisa-weekly-{week}":
        errs.append(f"id는 kisa-weekly-{week} 이어야 함 (지금 {data['id']})")
    try:
        start, published = Day.fromisoformat(week), Day.fromisoformat(data["published_date"])
        datetime.fromisoformat(data["generated_at"])
    except ValueError as e:
        return errs + [f"없는 날짜: {e}"]
    if start.weekday() != 0:
        errs.append(f"week_start는 월요일이어야 함 ({week}은 {R.DOW[start.weekday()]}요일)")
    end = R.week_end(start)
    if not end < published <= start + timedelta(days=31):
        errs.append(f"published_date {published}는 대상 주간이 끝난 뒤({end + timedelta(days=1)})부터 "
                    f"시작일+31일({start + timedelta(days=31)}) 사이여야 함")

    # 이전된 호 면제 — 표시 칸과 고정 목록이 둘 다 맞아야 한다
    prov = data["provenance"]
    exempt = week in MIGRATED_WEEKS
    if prov["type"] == "migrated":
        if not exempt:
            errs.append(f"면제 목록에 없는 주차({week})가 migrated 표시를 달고 있음 — 이전된 호는 "
                        "tools/kisa/validate.py의 MIGRATED_WEEKS에 있어야 함")
        expected = f"docs/kisa-cert/{R.out_name(week)}"
        if prov.get("source_html") != expected or not prov.get("source_commit"):
            errs.append(f"migrated 표시에는 source_html({expected})과 source_commit이 있어야 함")
    elif exempt:
        errs.append(f"면제 목록의 주차({week})인데 provenance.type이 migrated가 아님")
    if exempt and uses_structured(data):
        errs.append("이전된 호에는 구조화 칸(checks·vulnerabilities·notices·priority 등)을 쓰지 않음 — 새 호 규칙을 면제로 우회할 수 없음")
    if exempt and "priority" not in data:  # schema에서 필수를 뺐으므로(새 호는 쓰지 않음) 이전된 호는 여기서 강제
        errs.append("$.priority: 필수 칸 없음 — 이전된 호는 2. 우선순위 표를 priority[]로 적어야 함")
    if not exempt:
        errs += check_new_issue(data)  # 새 호 규칙(구조화 칸·출처·확인 기록)
        # 이전된 호에만 허용되는 것들 — 새 호에서는 계속 실패해야 함
        if data.get("boilerplate"):
            errs.append("고정 문구 바꿔 쓰기(boilerplate)는 이전된 호에만 허용")
        if any(not s["url"] for it in data["items"] for s in it["sources"]):
            errs.append("출처 URL이 빈 칸 — 이전된 호에만 허용")

    # 렌더 일치
    html_path = root / "docs" / "kisa-cert" / R.out_name(week)
    try:
        expected_html = R.render(data, rel)
    except R.RenderError as e:
        return errs + [f"렌더링 실패(본문 표기 오류 등): {e}"]
    if not html_path.exists():
        return errs + [f"HTML 없음: docs/kisa-cert/{html_path.name} — python tools/kisa/render.py {week}"]
    try:
        actual = lf(html_path.read_bytes())
    except UnicodeDecodeError:
        return errs + [f"HTML이 UTF-8이 아님: {html_path.name}"]
    if actual != expected_html:
        a, b = actual.split("\n"), expected_html.split("\n")
        n = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        errs.append(f"HTML이 데이터 렌더 결과와 다름 — {n + 1}번째 줄부터 다름. HTML을 직접 고치지 말고 "
                    f"데이터를 고친 뒤 python tools/kisa/render.py {week}\n"
                    f"      HTML: {a[n][:160] if n < len(a) else '(끝)'}\n"
                    f"      렌더: {b[n][:160] if n < len(b) else '(끝)'}")

    # HTML 필수 요소 (틀이 바뀌어도 빠지지 않게)
    if f'<meta name="portal-date" content="{published.isoformat()}">' not in actual:
        errs.append("HTML에 published_date와 같은 portal-date 메타가 없음")
    if R.NAV_TAG not in actual:
        errs.append("HTML에 상단 바 줄이 없음")
    if f"<title>{R.esc(R.title_of(start))}</title>" not in actual:
        errs.append("HTML 제목이 규칙과 다름")
    for sec in SECTIONS:
        if f">{sec}</h2>" not in actual:
            errs.append(f"HTML 구획 없음: {sec}")
    return errs


def check_folder(root: Path, weeks: set[str]) -> list[str]:
    errs = []
    folder = root / "docs" / "kisa-cert"
    made = {R.out_name(w) for w in weeks}
    for p in sorted(folder.glob("*.html")):
        if p.name == "index.html" or p.name in LEGACY_HTML or p.name in made:
            continue
        errs.append(f"docs/kisa-cert/{p.name}: 데이터(content/kisa-cert/*.json)에서 만든 파일이 아니고 레거시 목록에도 없음 "
                    "— 같은 주차 중복이거나 손으로 올린 파일")
    for name in sorted(made & LEGACY_HTML):
        errs.append(f"docs/kisa-cert/{name}: 데이터가 생겼으면 LEGACY_HTML 목록에서 빼야 함")
    return errs


# ── 새 호 규칙 (구조화 칸) ───────────────────────────────────────
# 새 호의 항목 머리 줄은 구조화 칸에서 렌더러가 만든다. 아래 check_new_issue()는 그 칸들의 규칙이다.
# check_issue()가 면제 목록 밖 주차(새 호)마다 부른다(tools/kisa/tests도 직접 부른다).
# 형식(칸 이름·상태 값·필수 칸)은 schema.json이 검사하므로 여기서는 schema를 통과한 데이터를 전제로 한다.

STRUCTURED_KEYS = ("vulnerabilities", "notices", "cve_total", "vendor_rating", "addition", "priority")
# 표의 deadline_note에 구조화 칸의 사실(번호·날짜·CVE·KEV·KISA)을 글자로 다시 적지 못하게 한다
FACT_IN_NOTE = re.compile(r"\d|[#＃]|CVE|KEV|KISA", re.IGNORECASE)
LEGACY_KEYS = ("meta", "meta_refs")
CVE_ID = re.compile(r"CVE-\d{4}-\d{4,}")
# 출처 종류별 허용 주소. vendor는 "이 네 종류의 주소가 아닐 것"만 본다.
RESERVED_HOSTS = {
    "kisa": [("www.boho.or.kr", "")],
    "kev": [("www.cisa.gov", ""), ("github.com", "/cisagov/kev-data"), ("raw.githubusercontent.com", "/cisagov/kev-data")],
    "nvd": [("nvd.nist.gov", "")],
    "cve": [("www.cve.org", ""), ("cveawg.mitre.org", "")],
}
CVSS_BASIS_KIND = {"vendor": "vendor", "nvd": "nvd", "cisa-adp": "cve"}  # cisa-adp = CVE 레코드 안의 CISA-ADP 평가
EXPLOIT_KINDS = {"confirmed": {"kev", "vendor", "kisa"}, "no_report": {"vendor", "kisa"}}
URGENT = ("긴급", "높음")


def split_url(url: str):
    """urlsplit — 해석할 수 없는 주소(예: 닫히지 않은 '[')면 예외 대신 None."""
    try:
        u = urlsplit(url)
        u.hostname  # 대괄호 주소 검사가 여기서 일어날 수 있음
        return u
    except ValueError:
        return None


def reserved_kind(url: str) -> str | None:
    """주소가 kisa·kev·nvd·cve 허용 주소 중 하나면 그 종류, 아니면 None(해석할 수 없는 주소 포함)."""
    u = split_url(url)
    if u is None:
        return None
    host, path = (u.hostname or "").lower(), u.path
    for kind, rules in RESERVED_HOSTS.items():
        for h, prefix in rules:
            if host == h and (not prefix or path == prefix or path.startswith(prefix + "/")):
                return kind
    return None


def uses_structured(data: dict) -> bool:
    return "checks" in data or any(k in it for it in data["items"] for k in STRUCTURED_KEYS)


class _Ctx:
    """한 호를 검사하는 동안 필요한 날짜·확인 기록·호 안 일관성 기록."""

    def __init__(self, data: dict, errs: list[str]):
        self.errs = errs
        self.start = Day.fromisoformat(data["week_start"])
        self.end = R.week_end(self.start)
        self.published = Day.fromisoformat(data["published_date"])
        checks = data.get("checks") or {}
        self.kev, self.kisa = checks.get("kev"), checks.get("kisa")
        self.catalog: Day | None = None
        self.kev_seen: dict[str, tuple] = {}   # CVE → (상태, 등재일, 기한)
        self.kisa_seen: dict[int, str] = {}    # KISA 번호 → 게시일

    def day(self, value: str, where: str) -> Day | None:
        try:
            return Day.fromisoformat(value)
        except ValueError:
            self.errs.append(f"{where}: 없는 날짜 {value!r}")
            return None

    def not_after_published(self, value: str, where: str) -> None:
        d = self.day(value, where)
        if d and d > self.published:
            self.errs.append(f"{where}: {d}는 발행일({self.published})보다 늦을 수 없음")


def _checked_at(value: str, where: str, errs: list[str]) -> None:
    """확인 시각이 실제로 있는 날짜·시각인지(모양은 schema.json이 본다)."""
    try:
        datetime.fromisoformat(value)
    except ValueError:
        errs.append(f"{where}: 없는 날짜·시각 {value!r}")


def check_new_issue(data: dict) -> list[str]:
    """새 호(구조화 칸) 규칙. schema.json 검사를 통과한 데이터를 받는다.
    schema를 통과한 데이터라면 어떤 경우에도 예외를 내지 않고 실패 메시지 목록을 돌려준다."""
    errs: list[str] = []
    try:
        ctx = _Ctx(data, errs)
    except ValueError as e:  # 모양은 맞지만 없는 날짜(week_start·published_date)
        return [f"없는 날짜: {e}"]
    if data["provenance"]["type"] != "generated":
        errs.append("새 호는 provenance.type이 generated여야 함")
    if "priority" in data:
        errs.append("새 호는 최상위 priority[]를 쓰지 않음 — 2. 우선순위 표는 각 항목의 priority 칸과 구조화 칸에서 만든다")

    # 호 단위 확인 기록 — "KEV 미등재"·"보호나라 대상 기간 공지 없음"의 근거
    if ctx.kev is None:
        errs.append("checks.kev(호 단위 KEV 확인 기록)가 없음")
    else:
        if reserved_kind(ctx.kev["url"]) != "kev":
            errs.append(f"checks.kev.url은 KEV 허용 주소여야 함: {ctx.kev['url']}")
        _checked_at(ctx.kev["checked_at"], "checks.kev.checked_at", errs)
        try:
            ctx.catalog = datetime.strptime(ctx.kev["catalog_version"], "%Y.%m.%d").date()
        except ValueError:
            errs.append(f"checks.kev.catalog_version이 없는 날짜: {ctx.kev['catalog_version']!r}")
        if ctx.catalog and ctx.catalog > ctx.published:
            errs.append(f"checks.kev: 판 날짜({ctx.catalog})가 발행일({ctx.published})보다 늦음")
    if ctx.kisa is None:
        errs.append("checks.kisa(호 단위 보호나라 확인 기록)가 없음")
    else:
        if reserved_kind(ctx.kisa["url"]) != "kisa":
            errs.append(f"checks.kisa.url은 보호나라 허용 주소여야 함: {ctx.kisa['url']}")
        _checked_at(ctx.kisa["checked_at"], "checks.kisa.checked_at", errs)
        ps = ctx.day(ctx.kisa["period_start"], "checks.kisa.period_start")
        pe = ctx.day(ctx.kisa["period_end"], "checks.kisa.period_end")
        if ps and pe and ps > pe:
            errs.append("checks.kisa: 확인 기간 시작이 끝보다 늦음")

    for i, it in enumerate(data["items"], 1):
        errs += [f"3-{i}: {e}" for e in _item_errors(it, data, ctx)]
    return errs


def _item_errors(it: dict, data: dict, ctx: _Ctx) -> list[str]:
    errs: list[str] = []
    outer, ctx.errs = ctx.errs, errs  # 날짜 오류를 이 항목 앞에 모으기 위해 잠시 바꿔 씀
    try:
        _item_rules(it, data, ctx, errs)
    finally:
        ctx.errs = outer
    return errs


def _item_rules(it: dict, data: dict, ctx: _Ctx, errs: list[str]) -> None:
    has_legacy = any(k in it for k in LEGACY_KEYS)
    if "vulnerabilities" not in it:
        errs.append("새 호 항목은 구조화 칸(vulnerabilities·notices)으로 써야 함 — meta·meta_refs 머리 줄은 이전된 호 전용")
        return
    if has_legacy:
        errs.append("구조화 칸과 meta·meta_refs를 한 항목에 함께 쓸 수 없음")
    if "priority" not in it:
        errs.append("새 호 항목에 priority(2. 우선순위 표 한 줄: target·details·deadline)가 없음")
    if "notices" not in it:  # meta·meta_refs가 있으면 schema는 통과하므로 여기서 멈춘다(아래는 notices 전제)
        errs.append("구조화 항목에 notices(KISA·벤더 공지)가 없음")
        return

    # 출처 — id·kind·viewed 필수, id 중복 금지, https, 종류별 주소
    srcs: dict[str, dict] = {}
    for n, s in enumerate(it["sources"], 1):
        where = f"출처 {n}({s['label']})"
        missing = [k for k in ("id", "kind", "viewed") if k not in s]
        if missing:
            errs.append(f"{where}: 새 호 출처에는 {', '.join(missing)} 칸이 필요함")
            continue
        if s["id"] in srcs:
            errs.append(f"{where}: 출처 id 중복 {s['id']!r}")
        srcs[s["id"]] = s
        u = split_url(s["url"])
        if u is None:
            errs.append(f"{where}: 주소를 해석할 수 없음 ({s['url']!r})")
            continue
        if u.scheme != "https" or not u.hostname:
            errs.append(f"{where}: 새 호 출처 주소는 https여야 함 ({s['url']!r})")
            continue
        rk = reserved_kind(s["url"])
        if s["kind"] in RESERVED_HOSTS and rk != s["kind"]:
            errs.append(f"{where}: {s['kind']} 출처인데 주소가 {s['kind']} 허용 주소가 아님 ({u.hostname})")
        elif s["kind"] == "vendor" and rk:
            errs.append(f"{where}: vendor 출처인데 주소가 {rk} 주소임 ({u.hostname})")

    def ref(src_id: str, allowed: set[str], what: str) -> None:
        s = srcs.get(src_id)
        if s is None:
            errs.append(f"{what}: 출처 {src_id!r}가 이 항목의 출처 목록에 없음")
        elif s["viewed"] is not True:
            errs.append(f"{what}: 출처 {src_id!r}는 미열람(viewed=false)이라 근거로 쓸 수 없음")
        elif s["kind"] not in allowed:
            errs.append(f"{what}: 출처 {src_id!r}의 종류 {s['kind']}는 근거로 쓸 수 없음(허용: {', '.join(sorted(allowed))})")

    # 취약점별 칸
    vulns = it["vulnerabilities"]
    ids: list[str] = []
    listed = False
    for n, v in enumerate(vulns, 1):
        cve, cvss, ex, kev = v["cve"], v["cvss"], v["exploitation"], v["kev"]
        name = cve.get("id") or f"취약점 {n}"
        if cve["state"] == "value":
            if cve["id"] in ids:
                errs.append(f"{name}: 같은 항목에 CVE 중복")
            ids.append(cve["id"])
            if int(cve["id"][4:8]) > ctx.published.year:
                errs.append(f"{name}: CVE 연도가 발행 연도({ctx.published.year})보다 늦음")

        if cvss["state"] == "value":
            score = cvss["score"]
            if not isinstance(score, float) or round(score, 1) != score:
                errs.append(f"{name}: CVSS 점수는 소수 한 자리로 적어야 함(예: 9.0) — 지금 {score!r}")
            kind = CVSS_BASIS_KIND[cvss["basis"]]
            ref(cvss["src"], {kind}, f"{name} CVSS(평가 주체 {cvss['basis']})")

        if ex["state"] in EXPLOIT_KINDS:
            ref(ex["src"], EXPLOIT_KINDS[ex["state"]], f"{name} 악용 {ex['state']}")
        if ex["state"] == "confirmed" and srcs.get(ex["src"], {}).get("kind") == "kev" and kev["state"] != "listed":
            errs.append(f"{name}: 악용 확인의 근거가 KEV인데 KEV 상태가 listed가 아님 (지금 {kev['state']})")
        if ex["state"] == "no_report":
            ctx.not_after_published(ex["as_of"], f"{name} 악용 no_report 기준일(as_of)")

        # KEV — CVE 상태에 따라 허용 상태가 정해진다. "미확인"은 CVE도 미확인일 때만.
        allowed_kev = {"value": ("listed", "not_listed"), "not_assigned": ("not_applicable",),
                       "unknown": ("unknown",)}[cve["state"]]
        if kev["state"] not in allowed_kev:
            errs.append(f"{name}: CVE 상태가 {cve['state']}이면 KEV 상태는 {' / '.join(allowed_kev)} 중 하나여야 함"
                        f" (지금 {kev['state']})")
        # checks.kev.complete=true의 뜻: 그 판본의 전체 KEV 목록을 확보했고, 이 호의 구조화 데이터에 기록된
        # 모든 CVE를 그 목록에서 조회했다. 기록하지 않은 CVE(cve_total 초과분)까지 조회했다는 뜻은 아니다 —
        # 그래서 일부만 기록한 항목의 머리 줄은 "KEV 미등재(기록 N건 기준)"으로 범위를 밝힌다(render.py).
        if kev["state"] == "not_listed" and not (ctx.kev and ctx.kev["complete"] is True):
            errs.append(f"{name}: KEV 미등재(not_listed)는 호 단위 KEV 확인 기록이 complete=true일 때만 쓸 수 있음")
        if kev["state"] == "listed":
            listed = True
            ref(kev["src"], {"kev"}, f"{name} KEV 등재")
            if ex["state"] != "confirmed":
                errs.append(f"{name}: KEV 등재인데 악용 상태가 confirmed가 아님 (지금 {ex['state']})")
            added = ctx.day(kev["added"], f"{name} KEV 등재일")
            due = ctx.day(kev["due"], f"{name} KEV 기한")
            if added and due and due < added:
                errs.append(f"{name}: KEV 기한({due})이 등재일({added})보다 앞섬")
            if added and added > ctx.published:
                errs.append(f"{name}: KEV 등재일({added})이 발행일({ctx.published})보다 늦음")
            if added and ctx.catalog and ctx.catalog < added:
                errs.append(f"{name}: KEV 판 날짜({ctx.catalog})가 등재일({added})보다 앞섬")
        if cve["state"] == "value":
            seen = (kev["state"], kev.get("added"), kev.get("due"))
            prev = ctx.kev_seen.setdefault(cve["id"], seen)
            if prev != seen:
                errs.append(f"{name}: 같은 호 안에서 KEV 기록이 다름 ({prev} ↔ {seen})")

    for cid in sorted(set(CVE_ID.findall(it["title"])) - set(ids)):
        errs.append(f"제목의 {cid}가 vulnerabilities 목록에 없음")
    if "cve_total" in it and it["cve_total"] < len(vulns):
        errs.append(f"cve_total({it['cve_total']})이 기록한 취약점 수({len(vulns)})보다 작음")
    if listed and it["severity"] not in URGENT:
        errs.append(f"KEV 등재 CVE가 있으면 위험도는 긴급·높음만 허용 (지금 {it['severity']})")
    note = it.get("priority", {}).get("deadline_note")
    if note is not None:
        if FACT_IN_NOTE.search(note):
            errs.append(f"priority.deadline_note에는 숫자·CVE·KEV·KISA·#를 쓸 수 없음 ({note!r}) — 사실은 구조화 칸에서 자동으로 나온다")
        if listed:
            errs.append("KEV 등재 항목에는 priority.deadline_note를 쓸 수 없음 — 그 자리에 KEV 기한이 자동으로 나온다")

    # 공지
    kisa = it["notices"]["kisa"]
    if kisa["state"] == "value":
        ref(kisa["src"], {"kisa"}, f"KISA #{kisa['no']}")
        ctx.not_after_published(kisa["posted"], f"KISA #{kisa['no']} 게시일")
        if ctx.kisa and kisa["no"] > ctx.kisa["last_no"]:
            errs.append(f"KISA #{kisa['no']}가 호 단위 확인 기록의 마지막 번호(#{ctx.kisa['last_no']})보다 큼")
        prev = ctx.kisa_seen.setdefault(kisa["no"], kisa["posted"])
        if prev != kisa["posted"]:
            errs.append(f"KISA #{kisa['no']}: 같은 호 안에서 게시일이 다름 ({prev} ↔ {kisa['posted']})")
    elif kisa["state"] == "none_in_period":  # 확인한 대상 기간의 보호나라 게시판에 일치하는 공지가 없었다
        k = ctx.kisa
        covers = (k is not None and k["complete"] is True
                  and k["period_start"] <= ctx.start.isoformat() and k["period_end"] >= ctx.end.isoformat())
        if not covers:
            errs.append("보호나라 대상 기간 공지 없음(none_in_period)은 호 단위 보호나라 확인 기록이 complete=true이고 "
                        f"대상 기간({ctx.start}~{ctx.end}) 전체를 덮을 때만 쓸 수 있음")
    vendor = it["notices"]["vendor"]
    if vendor["state"] == "value":
        for adv in vendor["advisories"]:
            ref(adv["src"], {"vendor"}, f"벤더 공지 {adv['id']}")
            if "date" in adv:
                ctx.not_after_published(adv["date"], f"벤더 공지 {adv['id']} 공지일")
    if "vendor_rating" in it:
        ref(it["vendor_rating"]["src"], {"vendor"}, "벤더 등급")
    if "addition" in it:
        posted = kisa.get("posted")
        if kisa["state"] != "value" or posted <= ctx.end.isoformat():
            errs.append(f"'{it['addition']}' 표시는 KISA 게시일이 대상 주간 끝({ctx.end}) 이후일 때만 쓸 수 있음")


def report(where: str, errs: list[str]) -> None:
    for e in errs:
        first, *rest = e.splitlines()
        print(f"::error file={where}::{first}" if IN_ACTIONS else f"  실패: {first}")
        for line in rest:
            print(line)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description="KISA 주간 리포트 검사(구조·렌더 일치)")
    ap.add_argument("weeks", nargs="*", help="검사할 week_start (생략하면 전부)")
    ap.add_argument("--root", default=str(CODE), help="데이터·HTML이 있는 작업 트리 (기본: 이 저장소)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    files = sorted((root / "content" / "kisa-cert").glob("*.json"))
    if args.weeks:
        files = [f for f in files if f.stem in args.weeks]
        missing = set(args.weeks) - {f.stem for f in files}
        if missing:
            print(f"실패: 데이터 없음: {', '.join(sorted(missing))}")
            return 1

    failed = 0
    for f in files:
        rel = f.relative_to(root).as_posix()
        try:
            errs = check_issue(root, f, schema)
        except SchemaBug as e:
            print(f"검사기 오류: {e}")
            return 1
        print(f"{'통과' if not errs else '실패'}: {rel}" +
              (" (이전된 호)" if f.stem in MIGRATED_WEEKS and not errs else ""))
        report(rel, errs)
        failed += bool(errs)

    folder_errs = check_folder(root, {f.stem for f in sorted((root / "content" / "kisa-cert").glob("*.json"))})
    print(f"{'통과' if not folder_errs else '실패'}: docs/kisa-cert/ 폴더 (레거시 {len(LEGACY_HTML)}건 제외)")
    report("docs/kisa-cert", folder_errs)
    failed += bool(folder_errs)

    print(f"결과: {'통과' if not failed else f'실패 {failed}건'} — 검사한 호 {len(files)}건")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
