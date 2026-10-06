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
     목록 밖 주차는 아직 통과시키지 않는다 — 새 호에 필요한 구조화 칸과 근거 검사는 STEP 4·5에서 구현.
  4. 렌더 일치: HTML = 데이터를 틀에 넣어 다시 만든 결과 (줄바꿈 CRLF/LF 차이만 무시, 나머지는 바이트 단위)
  5. HTML 필수 요소: portal-date 메타, 상단 바 줄, 구획 제목
  6. 폴더: docs/kisa-cert/의 HTML은 레거시 목록에 있거나 데이터에서 만든 것이어야 한다(같은 주차 중복 금지)

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

CODE = Path(__file__).resolve().parents[2]       # 검사 코드·스키마·틀이 있는 쪽
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
NOT_YET = ("새 호 검사는 아직 지원하지 않음 — 새 호에 필요한 구조화 칸(위험도·CVSS·KISA 번호·게시일·KEV)과 "
           "근거 검사가 STEP 4·5에서 구현될 때까지 이 데이터는 게시할 수 없습니다")


# ── 스키마 검사 (schema.json에 쓰인 키워드만 해석, 모르는 키워드는 검사기 오류) ──────────
ANNOTATIONS = {"$schema", "$id", "title", "description", "$defs"}
KEYWORDS = {"type", "required", "properties", "additionalProperties", "items", "minItems",
            "minLength", "pattern", "enum", "const", "oneOf", "$ref"}
TYPES = {"object": dict, "array": list, "string": str}


class SchemaBug(Exception):
    pass


def schema_errors(value, schema: dict, root: dict, path: str = "$") -> list[str]:
    unknown = set(schema) - KEYWORDS - ANNOTATIONS
    if unknown:
        raise SchemaBug(f"schema.json에 검사기가 모르는 키워드: {sorted(unknown)} ({path})")
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            raise SchemaBug(f"지원하지 않는 $ref: {ref}")
        return schema_errors(value, root["$defs"][ref[8:]], root, path)
    if "oneOf" in schema:
        ok = [alt for alt in schema["oneOf"] if not schema_errors(value, alt, root, path)]
        return [] if len(ok) == 1 else [f"{path}: 허용된 형식 중 정확히 하나에 맞아야 함({len(ok)}개 일치)"]
    errs: list[str] = []
    if "const" in schema and value != schema["const"]:
        errs.append(f"{path}: {schema['const']!r} 이어야 함")
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} 는 허용 값({', '.join(map(str, schema['enum']))})이 아님")
    t = schema.get("type")
    if t:
        if not isinstance(value, TYPES[t]):
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
    if not exempt:
        errs.append(NOT_YET)
        # 이전된 호에만 허용되는 것들 — STEP 4·5 이후에도 새 호에서는 계속 실패해야 함
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
