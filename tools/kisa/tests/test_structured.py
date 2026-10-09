"""
KISA 새 호(구조화 칸) 시험 — 표준 라이브러리만, 네트워크 없음.

  python -m unittest discover -s tools/kisa/tests -v

시험용 데이터는 tools/kisa/tests/fixtures/new_issue.json(가상의 2026-10-05 주 호)이다.
실패 사례는 이 데이터를 복사해 한 곳씩 바꿔 만든다. content/·docs/에는 아무것도 쓰지 않는다.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "tools" / "kisa"))
import render as R  # noqa: E402
import validate as V  # noqa: E402

SCHEMA = json.loads(V.SCHEMA.read_text(encoding="utf-8"))
BASE = json.loads((HERE / "fixtures" / "new_issue.json").read_text(encoding="utf-8"))
A, B, C, D, E = range(5)  # 시험 데이터의 항목 순서: Cisco 형, Citrix 형, 일부 기록형, 파이오링크형, Tomcat 형


def fresh() -> dict:
    return copy.deepcopy(BASE)


def errors(data: dict) -> list[str]:
    """형식(schema.json) → 새 호 규칙 순서로 검사. 형식이 틀리면 형식 오류만 돌려준다(validate.py와 같음)."""
    return V.schema_errors(data, SCHEMA, SCHEMA) or V.check_new_issue(data)


def headline(data: dict, i: int) -> str:
    front, back = R.structured_headline(data["items"][i], date.fromisoformat(data["published_date"]))
    return f"{data['items'][i]['severity']} · {front} | {back}"


def run(*args: str) -> subprocess.CompletedProcess:
    # GitHub Actions 안에서는 validate.py가 실패를 '::error' 형식으로 찍는다. 시험은 출력 줄을 비교하므로
    # CI·로컬에서 같은 형식이 나오게 이 변수를 빼고 실행한다.
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"}
    return subprocess.run([sys.executable, *args], cwd=REPO, capture_output=True, env=env)


def validate_new_week(data: dict, html_edit=None) -> tuple[int, str]:
    """새 임시 작업 트리에 data를 2026-10-05 주차로 넣고 렌더한 HTML과 함께 validate.py --root 로 검사한다.
    html_edit가 있으면 렌더한 HTML 글자에 적용한 뒤 저장한다."""
    with tempfile.TemporaryDirectory(prefix="kisa-new-") as tmp:
        root = Path(tmp)
        (root / "content/kisa-cert").mkdir(parents=True)
        (root / "docs/kisa-cert").mkdir(parents=True)
        rel = "content/kisa-cert/2026-10-05.json"
        (root / rel).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        try:
            html = R.render(data, rel)
        except R.RenderError:  # 렌더할 수 없는 데이터(예: 글자 머리 줄로 바꾼 새 호) — 원래 가상 호의 HTML을 둔다
            html = R.render(BASE, rel)
        if html_edit:
            html = html_edit(html)
        with open(root / "docs/kisa-cert" / R.out_name("2026-10-05"), "w", encoding="utf-8", newline="\n") as f:
            f.write(html)
        out = run("tools/kisa/validate.py", "--root", tmp)
    return out.returncode, out.stdout.decode("utf-8")


class Compatibility(unittest.TestCase):
    def test_01_0928_render_is_byte_identical(self):
        out = run("tools/kisa/render.py", "2026-09-28", "--stdout")
        self.assertEqual(out.returncode, 0, out.stderr.decode("utf-8", "replace"))
        published = (REPO / "docs/kisa-cert/kisa_weekly_2026-09-28_public.html").read_bytes()
        self.assertEqual(out.stdout, published)

    def test_02_new_week_passes_in_validate_flow(self):
        # 관문을 연 뒤(WP4-C2): 가상 새 호가 실제 validate.py 흐름을 끝까지 통과한다.
        # (관문을 열기 전에는 "새 호 검사는 아직 지원하지 않음" 한 줄로 실패하는 것을 확인하던 시험)
        code, text = validate_new_week(BASE)
        self.assertEqual(code, 0, text)
        self.assertIn("통과: content/kisa-cert/2026-10-05.json", text)
        self.assertEqual([ln for ln in text.splitlines() if "실패" in ln], [], text)

    def test_migrated_issue_cannot_use_structured_fields(self):
        data = json.loads((REPO / "content/kisa-cert/2026-09-28.json").read_text(encoding="utf-8"))
        data["checks"] = copy.deepcopy(BASE["checks"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "content/kisa-cert").mkdir(parents=True)
            (root / "docs/kisa-cert").mkdir(parents=True)
            path = root / "content/kisa-cert/2026-09-28.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            html = (REPO / "docs/kisa-cert/kisa_weekly_2026-09-28_public.html").read_bytes()
            (root / "docs/kisa-cert/kisa_weekly_2026-09-28_public.html").write_bytes(html)
            errs = V.check_issue(root, path, SCHEMA)
        self.assertTrue(any("이전된 호에는 구조화 칸" in e for e in errs), errs)


class Headlines(unittest.TestCase):
    def test_base_fixture_passes(self):
        self.assertEqual(errors(fresh()), [])

    def test_03_cisco_type(self):
        self.assertEqual(headline(BASE, A),
                         "긴급 · CVSS 9.8 · 악용 확인 | KISA #9001(10/7 게시) · 벤더 공지 10/5 · KEV 등재 10/6(기한 10/9)")

    def test_04_citrix_type(self):
        self.assertEqual(headline(BASE, B),
                         "긴급 · CVSS 최대 9.5(v4.0) · 2건 악용 확인 | KISA #9002(10/8 게시) · 벤더 공지 10/6 · "
                         "KEV 등재 10/10(기한 10/31)")

    def test_05_partially_recorded(self):
        self.assertEqual(headline(BASE, C),
                         "긴급 · CVSS 9.8(NVD) · 2건 악용 확인 | KISA #9003(10/9 게시) · 벤더 공지 10/2 · "
                         "KEV 등재 2건(가장 이른 기한 10/27)")

    def test_06_no_cve_type(self):
        self.assertEqual(headline(BASE, D),
                         "긴급 · CVSS [미확인] · 악용 확인 | KISA #9004(10/8 게시) · 벤더 공지 10/7 · KEV 해당 없음")

    def test_07_vendor_rating_type(self):
        self.assertEqual(headline(BASE, E),
                         "높음 · CVSS [미확인] · 벤더 등급 Important 4건 · 악용 [미확인] | KISA #9005(10/9 게시) · "
                         "벤더 공지 9/25 · KEV 미등재(기록 4건 기준)")  # 전체 12건 중 4건만 기록 → 범위를 밝힘

    def test_kev_not_listed_when_all_recorded(self):
        data = fresh()
        del data["items"][E]["cve_total"]  # 기록한 4건이 전체
        self.assertEqual(errors(data), [])
        self.assertTrue(headline(data, E).endswith("· KEV 미등재"), headline(data, E))

    def test_rendered_html_carries_headline(self):
        html = R.render(BASE)
        self.assertIn('<b style="color:#9B1C1C;">긴급</b> · CVSS 9.8 · 악용 확인  <span style="color:#9CA3AF;">|</span>  '
                      "KISA #9001(10/7 게시) · 벤더 공지 10/5 · KEV 등재 10/6(기한 10/9)</div>", html)
        self.assertIn('CVSS <span style="color:#6B7280;">[미확인]</span>', html)  # [미확인]은 회색

    def test_kisa_none_in_period_and_year_suffix(self):
        data = fresh()
        it = data["items"][A]
        it["notices"]["kisa"] = {"state": "none_in_period"}
        it["notices"]["vendor"]["advisories"][0]["date"] = "2025-12-30"
        it["sources"] = [s for s in it["sources"] if s["id"] != "kisa"]
        self.assertEqual(errors(data), [])
        self.assertEqual(headline(data, A),
                         "긴급 · CVSS 9.8 · 악용 확인 | 보호나라 대상 기간 공지 없음 · 벤더 공지 2025/12/30 · "
                         "KEV 등재 10/6(기한 10/9)")


class Rules(unittest.TestCase):
    def assertFails(self, data: dict, needle: str):
        errs = errors(data)
        self.assertTrue(any(needle in e for e in errs), f"'{needle}' 없음: {errs}")

    def test_08_kev_listed_but_no_report(self):  # 2026-09-28 호 Adobe 오류 사례
        data = fresh()
        data["items"][A]["vulnerabilities"][0]["exploitation"] = {"state": "no_report", "src": "vendor-a", "as_of": "2026-08-11"}
        self.assertFails(data, "KEV 등재인데 악용 상태가 confirmed가 아님")

    def test_09_unknowns_and_missing_records(self):
        data = fresh()
        data["items"][A]["vulnerabilities"][0]["kev"] = {"state": "unknown"}
        self.assertFails(data, "KEV 상태는 listed / not_listed 중 하나")
        data = fresh()
        data["items"][A]["notices"]["kisa"] = {"state": "unknown"}
        self.assertFails(data, "notices.kisa")
        data = fresh()
        del data["checks"]
        self.assertFails(data, "checks.kev(호 단위 KEV 확인 기록)가 없음")
        self.assertFails(data, "checks.kisa(호 단위 보호나라 확인 기록)가 없음")

    def test_10_negative_findings_need_complete_records(self):
        data = fresh()
        data["checks"]["kev"]["complete"] = False
        self.assertFails(data, "KEV 미등재(not_listed)는 호 단위 KEV 확인 기록이 complete=true일 때만")
        data = fresh()
        data["items"][A]["notices"]["kisa"] = {"state": "none_in_period"}
        data["checks"]["kisa"]["period_start"] = "2026-10-06"
        self.assertFails(data, "대상 기간(2026-10-05~2026-10-11) 전체를 덮을 때만")
        data = fresh()
        data["items"][A]["notices"]["kisa"] = {"state": "none_in_period"}
        data["checks"]["kisa"]["complete"] = False
        self.assertFails(data, "보호나라 대상 기간 공지 없음(none_in_period)")

    def test_11_source_restrictions(self):
        data = fresh()
        data["items"][A]["sources"][0]["viewed"] = False
        self.assertFails(data, "미열람(viewed=false)이라 근거로 쓸 수 없음")
        for kind in ("research", "news"):
            data = fresh()
            it = data["items"][A]
            it["sources"].append({"id": "blog", "kind": kind, "viewed": True, "label": "분석 글", "url": "https://blog.example/x"})
            it["vulnerabilities"][0]["cvss"]["src"] = "blog"
            self.assertFails(data, f"종류 {kind}는 근거로 쓸 수 없음")
            data = fresh()
            it = data["items"][D]
            it["sources"].append({"id": "blog", "kind": kind, "viewed": True, "label": "분석 글", "url": "https://blog.example/x"})
            it["vulnerabilities"][0]["exploitation"]["src"] = "blog"
            self.assertFails(data, f"종류 {kind}는 근거로 쓸 수 없음")

    def test_12_kev_date_order(self):
        data = fresh()
        data["items"][A]["vulnerabilities"][0]["kev"]["due"] = "2026-10-05"
        self.assertFails(data, "KEV 기한(2026-10-05)이 등재일(2026-10-06)보다 앞섬")
        data = fresh()
        data["checks"]["kev"]["catalog_version"] = "2026.10.05"
        self.assertFails(data, "KEV 판 날짜(2026-10-05)가 등재일(2026-10-06)보다 앞섬")
        data = fresh()
        data["items"][A]["vulnerabilities"][0]["kev"].update(added="2026-10-13", due="2026-10-16")
        self.assertFails(data, "KEV 등재일(2026-10-13)이 발행일(2026-10-12)보다 늦음")

    def test_13_kev_due_after_published_is_fine(self):
        data = fresh()
        data["items"][A]["vulnerabilities"][0]["kev"]["due"] = "2026-11-30"
        self.assertEqual(errors(data), [])

    @staticmethod
    def no_report_everywhere(data: dict, with_as_of: bool = True) -> None:
        for x, d in zip(data["items"][E]["vulnerabilities"], ("2026-10-03", "2026-10-02", "2026-10-04", "2026-10-03")):
            x["exploitation"] = {"state": "no_report", "src": "vendor-e", **({"as_of": d} if with_as_of else {})}

    def test_14_no_report_needs_as_of(self):
        data = fresh()
        del data["items"][E]["cve_total"]  # 기록한 4건이 전체
        self.no_report_everywhere(data, with_as_of=False)
        self.assertFails(data, "as_of")
        self.no_report_everywhere(data)
        self.assertEqual(errors(data), [])
        self.assertIn(" · 보고 없음(10/2 기준) | ", headline(data, E))

    def test_no_report_partially_recorded(self):
        data = fresh()  # 전체 12건 중 4건만 기록, 기록한 것은 모두 보고 없음
        self.no_report_everywhere(data)
        self.assertEqual(errors(data), [])
        self.assertIn(" · 보고 없음(기록 4건 · 10/2 기준) | ", headline(data, E))

    def test_15_shape_and_cve_list(self):
        data = fresh()
        data["items"][A]["meta"] = "CVSS 9.8 · 악용 확인"
        data["items"][A]["meta_refs"] = "KISA #9001"
        self.assertFails(data, "정확히 하나에 맞아야 함(2개 일치)")
        data = fresh()
        data["items"][A]["title"] += " · CVE-2026-9999999"
        self.assertFails(data, "제목의 CVE-2026-9999999가 vulnerabilities 목록에 없음")
        data = fresh()
        vs = data["items"][E]["vulnerabilities"]
        vs[1]["cve"]["id"] = vs[0]["cve"]["id"]
        self.assertFails(data, "같은 항목에 CVE 중복")
        data = fresh()
        data["items"][B]["cve_total"] = 2
        self.assertFails(data, "cve_total(2)이 기록한 취약점 수(8)보다 작음")

    def test_16_source_addresses(self):
        data = fresh()
        data["items"][A]["sources"][1]["url"] = "https://boho-or-kr.example/notice/9001"
        self.assertFails(data, "kisa 출처인데 주소가 kisa 허용 주소가 아님")
        data = fresh()
        data["items"][A]["sources"][0]["url"] = "https://nvd.nist.gov/vuln/detail/CVE-2026-9990001"
        self.assertFails(data, "vendor 출처인데 주소가 nvd 주소임")
        data = fresh()
        data["items"][A]["vulnerabilities"][0]["cvss"]["basis"] = "nvd"
        self.assertFails(data, "CVSS(평가 주체 nvd): 출처 'vendor-a'의 종류 vendor는 근거로 쓸 수 없음")

    def test_17_kev_listed_needs_urgent_or_high(self):
        data = fresh()
        data["items"][A]["severity"] = "보통"
        self.assertFails(data, "KEV 등재 CVE가 있으면 위험도는 긴급·높음만 허용")

    def test_18_vendor_date_after_kisa_is_not_a_failure(self):
        data = fresh()
        data["items"][A]["notices"]["vendor"]["advisories"][0]["date"] = "2026-10-09"  # KISA 게시 10/7보다 늦음
        self.assertEqual(errors(data), [])

    def test_more_consistency_rules(self):
        data = fresh()  # 같은 CVE의 KEV 기록은 호 안에서 같아야 함
        data["items"][C]["title"] = "시험 제품 C 6건 — CVE-2026-9990001 외"
        data["items"][C]["vulnerabilities"][0]["cve"]["id"] = "CVE-2026-9990001"
        self.assertFails(data, "같은 호 안에서 KEV 기록이 다름")
        data = fresh()  # 같은 KISA 번호의 게시일은 같아야 함
        data["items"][B]["notices"]["kisa"]["no"] = 9001
        self.assertFails(data, "KISA #9001: 같은 호 안에서 게시일이 다름")
        data = fresh()
        data["checks"]["kisa"]["last_no"] = 9004
        self.assertFails(data, "KISA #9005가 호 단위 확인 기록의 마지막 번호(#9004)보다 큼")
        data = fresh()
        data["items"][D]["vulnerabilities"][0]["kev"] = {"state": "not_listed"}
        self.assertFails(data, "CVE 상태가 not_assigned이면 KEV 상태는 not_applicable")
        data = fresh()
        data["items"][A]["vulnerabilities"][0]["cvss"]["score"] = 9
        self.assertFails(data, "소수 한 자리")
        data = fresh()
        data["items"][A]["addition"] = "긴급 추가"
        self.assertFails(data, "'긴급 추가' 표시는 KISA 게시일이 대상 주간 끝(2026-10-11) 이후일 때만")
        data = fresh()
        data["items"][E]["cve_total"] = True  # 참/거짓은 정수가 아님
        self.assertFails(data, "integer 이어야 함")
        data = fresh()
        data["items"][A]["sources"][0]["url"] = ""
        self.assertFails(data, "https여야 함")


class RuleGaps(unittest.TestCase):
    """코드 검토에서 나온 여섯 가지(fix/kisa-rule-gaps)."""

    assertFails = Rules.assertFails

    # 1. checked_at은 실제로 있는 날짜·시각이어야 함
    def test_gap1_kev_checked_at_impossible(self):
        data = fresh()
        data["checks"]["kev"]["checked_at"] = "2026-99-99T88:77:66+09:00"
        self.assertEqual(V.schema_errors(data, SCHEMA, SCHEMA), [])  # 모양은 맞음
        self.assertFails(data, "checks.kev.checked_at: 없는 날짜·시각")

    def test_gap1_kisa_checked_at_impossible(self):
        data = fresh()
        data["checks"]["kisa"]["checked_at"] = "2026-99-99T88:77:66+09:00"
        self.assertFails(data, "checks.kisa.checked_at: 없는 날짜·시각")

    # 2. notices.kisa의 "대상 기간 공지 없음"은 none_in_period
    def test_gap2_none_in_period_passes_with_same_wording(self):
        data = fresh()
        data["items"][E]["notices"]["kisa"] = {"state": "none_in_period"}
        self.assertEqual(errors(data), [])
        self.assertIn(" | 보호나라 대상 기간 공지 없음 · 벤더 공지 9/25 · ", headline(data, E))

    def test_gap2_old_name_not_applicable_fails(self):
        data = fresh()
        data["items"][E]["notices"]["kisa"] = {"state": "not_applicable"}
        self.assertFails(data, "$.items[4].notices.kisa")

    # 3. KEV 원본 파일 주소(raw.githubusercontent.com/cisagov/kev-data)
    RAW_KEV = "https://raw.githubusercontent.com/cisagov/kev-data/main/known_exploited_vulnerabilities.json"

    def test_gap3_raw_kev_url_allowed_for_kev(self):
        data = fresh()
        data["items"][A]["sources"][2]["url"] = self.RAW_KEV
        data["checks"]["kev"]["url"] = self.RAW_KEV
        self.assertEqual(errors(data), [])

    def test_gap3_raw_kev_url_rejected_as_vendor(self):
        data = fresh()
        data["items"][A]["sources"][0]["url"] = self.RAW_KEV
        self.assertFails(data, "vendor 출처인데 주소가 kev 주소임")

    # 4. 악용 확인의 근거가 KEV면 KEV 상태는 listed
    def test_gap4_kev_based_confirmed_needs_listed(self):
        data = fresh()
        data["items"][B]["vulnerabilities"][2]["exploitation"] = {"state": "confirmed", "src": "kev"}  # kev=not_listed
        self.assertFails(data, "악용 확인의 근거가 KEV인데 KEV 상태가 listed가 아님 (지금 not_listed)")

    def test_gap4_vendor_based_confirmed_with_not_listed_passes(self):
        data = fresh()
        data["items"][B]["vulnerabilities"][2]["exploitation"] = {"state": "confirmed", "src": "vendor-b"}
        self.assertEqual(errors(data), [])

    # 5. schema를 통과한 데이터에는 예외 없이 실패 목록
    def test_gap5_mixed_item_without_notices_returns_errors(self):
        data = fresh()
        it = data["items"][A]
        it["meta"], it["meta_refs"] = "CVSS 9.8 · 악용 확인", "KISA #9001"
        del it["notices"]
        self.assertEqual(V.schema_errors(data, SCHEMA, SCHEMA), [])  # 이 조합은 schema를 통과한다
        errs = V.check_new_issue(data)  # 예외가 나면 시험 오류
        self.assertTrue(any("함께 쓸 수 없음" in e for e in errs), errs)
        self.assertTrue(any("notices(KISA·벤더 공지)가 없음" in e for e in errs), errs)

    def test_gap5_other_schema_valid_oddities_return_errors(self):
        data = fresh()  # 모양은 맞지만 없는 날짜
        data["week_start"] = "2026-13-45"
        self.assertEqual(V.schema_errors(data, SCHEMA, SCHEMA), [])
        self.assertTrue(V.check_new_issue(data))
        data = fresh()  # 해석할 수 없는 주소(닫히지 않은 대괄호)
        data["items"][A]["sources"][0]["url"] = "https://[vendor-a.example/x"
        data["checks"]["kev"]["url"] = "https://[www.cisa.gov/x"
        self.assertEqual(V.schema_errors(data, SCHEMA, SCHEMA), [])
        errs = V.check_new_issue(data)
        self.assertTrue(any("주소를 해석할 수 없음" in e for e in errs), errs)
        self.assertTrue(any("checks.kev.url은 KEV 허용 주소여야 함" in e for e in errs), errs)

    # 6. $ref 옆의 검사 키워드는 SchemaBug
    def test_gap6_ref_with_sibling_keyword_raises(self):
        root = {"$defs": {"word": {"type": "string"}}}
        with self.assertRaises(V.SchemaBug):
            V.schema_errors("abc", {"$ref": "#/$defs/word", "pattern": "^z"}, root)

    def test_gap6_ref_with_description_is_fine(self):
        root = {"$defs": {"word": {"type": "string"}}}
        self.assertEqual(V.schema_errors("abc", {"$ref": "#/$defs/word", "description": "설명"}, root), [])


class OpenGate(unittest.TestCase):
    """WP4-C2 — 관문을 연 뒤 실제 validate.py 흐름(--root)에서 새 호를 검사한다. 끝에서 끝까지 통과는 test_02."""

    def assertFlowFails(self, data: dict, *needles: str, html_edit=None):
        code, text = validate_new_week(data, html_edit)
        self.assertEqual(code, 1, text)
        self.assertIn("실패: content/kisa-cert/2026-10-05.json", text)
        for n in needles:
            self.assertIn(n, text)

    def test_g2_html_one_char_edit_fails(self):
        self.assertFlowFails(BASE, "HTML이 데이터 렌더 결과와 다름",
                             html_edit=lambda h: h.replace("Example Gateway A", "Example Gateway X", 1))

    def test_g3_rule_violation_fails_in_flow(self):
        data = fresh()  # KEV 등재인데 악용 no_report — 2026-09-28 호 Adobe 오류 사례
        data["items"][A]["vulnerabilities"][0]["exploitation"] = {"state": "no_report", "src": "vendor-a", "as_of": "2026-10-05"}
        self.assertFlowFails(data, "3-1: CVE-2026-9990001: KEV 등재인데 악용 상태가 confirmed가 아님")

    def test_g4_new_issue_marked_migrated_fails(self):
        data = fresh()
        data["provenance"] = {"type": "migrated", "source_html": "docs/kisa-cert/kisa_weekly_2026-10-05_public.html",
                              "source_commit": "0000000"}
        self.assertFlowFails(data, "면제 목록에 없는 주차(2026-10-05)가 migrated 표시를 달고 있음",
                             "새 호는 provenance.type이 generated여야 함")

    def test_g4_new_issue_with_text_headline_fails(self):
        data = fresh()
        it = data["items"][A]
        for k in ("vulnerabilities", "notices", "priority"):
            del it[k]
        it["meta"], it["meta_refs"] = "CVSS 9.8 · 악용 확인", "KISA #9001(10/7 게시)"
        self.assertFlowFails(data, "3-1: 새 호 항목은 구조화 칸(vulnerabilities·notices)으로 써야 함")

    def test_g4_new_issue_empty_source_url_fails(self):
        data = fresh()
        data["items"][A]["sources"][0]["url"] = ""
        self.assertFlowFails(data, "출처 URL이 빈 칸 — 이전된 호에만 허용", "새 호 출처 주소는 https여야 함")

    def test_g4_new_issue_boilerplate_fails(self):
        data = fresh()
        data["boilerplate"] = {"footer_notice": "바꿔 쓴 안내문"}
        self.assertFlowFails(data, "고정 문구 바꿔 쓰기(boilerplate)는 이전된 호에만 허용")

    def test_g5_migrated_0928_still_passes(self):
        out = run("tools/kisa/validate.py", "2026-09-28")
        text = out.stdout.decode("utf-8")
        self.assertEqual(out.returncode, 0, text)
        self.assertIn("통과: content/kisa-cert/2026-09-28.json (이전된 호)", text)
        # 렌더 바이트 일치는 test_01

    def test_g6_transitional_legacy_html_still_passes(self):
        # 과도기 절차: 데이터 없이 HTML만 있고 LEGACY_HTML에 등록된 파일은 지금처럼 통과
        with tempfile.TemporaryDirectory(prefix="kisa-legacy-") as tmp:
            root = Path(tmp)
            for sub in ("content/kisa-cert", "docs/kisa-cert"):
                shutil.copytree(REPO / sub, root / sub)
            for name in V.LEGACY_HTML:
                self.assertTrue((root / "docs/kisa-cert" / name).exists(), name)
            weeks = {p.stem for p in (root / "content/kisa-cert").glob("*.json")}
            self.assertFalse({R.out_name(w) for w in weeks} & V.LEGACY_HTML)  # 레거시 HTML에는 데이터가 없음
            out = run("tools/kisa/validate.py", "--root", tmp)
        text = out.stdout.decode("utf-8")
        self.assertEqual(out.returncode, 0, text)
        self.assertIn(f"통과: docs/kisa-cert/ 폴더 (레거시 {len(V.LEGACY_HTML)}건 제외)", text)


def row(data: dict, i: int) -> dict:
    return R.structured_priority_row(data["items"][i], date.fromisoformat(data["published_date"]))


def cells(r: dict) -> tuple[str, str, str, str]:
    """표 한 줄을 네 칸의 글자로(회색 줄은 ' / '로 이음)."""
    target = r["target"] + (f" / {r['target_note']}" if r["target_note"] else "")
    vuln = " / ".join([r["vuln"]] + r["vuln_details"])
    risk = " / ".join([r["severity"], r["cvss"], r["exploitation"]] + r["exploitation_notes"])
    due = r["deadline"] + (f" / {r['deadline_note']}" if r["deadline_note"] else "")
    return target, vuln, risk, due


class PriorityTable(unittest.TestCase):
    """WP4-B — 새 호의 2. 우선순위 표를 항목의 구조화 칸에서 만든다."""

    assertFails = Rules.assertFails

    # 1. 다섯 유형의 표 한 줄
    def test_p1_cisco_type(self):
        self.assertEqual(cells(row(BASE, A)), (
            "Example Gateway A / KISA #9001 · KEV 10/6",
            "**CVE-2026-9990001** / 가상 입력값 검증 결함 → 인증 없는 명령 실행 / ▸ Example Gateway A 1.x / 2.x 계열",
            "긴급 / CVSS 9.8 / ● 악용 확인 · KEV 10/6",
            "즉시 / KEV 기한 10/9 경과"))

    def test_p1_citrix_type(self):
        self.assertEqual(cells(row(BASE, B)), (
            "Example Appliance B / KISA #9002 · KEV 10/10",
            "**CVE-2026-9990011** 외 7건 / 가상 메모리 결함 → 원격 코드 실행 / ▸ 기본 구성 전체 해당",
            "긴급 / CVSS 최대 9.5(v4.0) / ● 2건 악용 확인 · KEV 10/10",
            "즉시 / KEV 기한 10/31"))

    def test_p1_partially_recorded(self):
        self.assertEqual(cells(row(BASE, C)), (
            "Example Product C / KISA #9003 · KEV 2건",
            "**CVE-2026-9990021** 외 5건 / 가상 인증 우회 → 관리자 권한 획득",
            "긴급 / CVSS 9.8(NVD) / ● 2건 악용 확인 · KEV 2건",
            "즉시 / KEV 기한 10/27"))

    def test_p1_no_cve_type(self):
        self.assertEqual(cells(row(BASE, D)), (
            "Example Switch D / KISA #9004",
            "CVE 미부여 / 가상 구버전 취약점 → 원격 명령 실행",
            "긴급 / CVSS [미확인] / ● 악용 확인 / 벤더 확인",
            "즉시 / 해당 시"))

    def test_p1_vendor_rating_type(self):
        self.assertEqual(cells(row(BASE, E)), (
            "Example Middleware E / KISA #9005",
            "**CVE-2026-9990031** 외 11건 / 가상 요청 처리 결함 묶음 / ▸ Example Middleware E 3.x 계열",
            "높음 / CVSS [미확인] · 벤더 등급 Important 4건 / ◌ 악용 [미확인]",
            "2주 / 정기 창"))

    def test_p1_rendered_html_row(self):
        html = R.render(BASE)
        self.assertIn('<td style="border:1px solid #D1D5DB;word-break:keep-all;"><b>Example Gateway A</b><br>'
                      '<span style="color:#6B7280;">KISA #9001 · KEV 10/6</span></td>', html)
        self.assertIn('<b style="color:#9B1C1C;">긴급</b><br><span style="color:#6B7280;">CVSS 9.8</span><br>'
                      '<b>● 악용 확인 · KEV 10/6</b></td>', html)
        self.assertIn('<b>즉시</b><br><span style="color:#6B7280;">KEV 기한 10/9 경과</span></td>', html)

    # 2. 머리 줄과 표가 같은 CVSS·악용·KEV 문구
    def test_p2_headline_and_table_share_wording(self):
        published = date.fromisoformat(BASE["published_date"])
        for i, it in enumerate(BASE["items"]):
            with self.subTest(item=i):
                front, back = R.structured_headline(it, published)
                r = row(BASE, i)
                vulns, total = it["vulnerabilities"], it.get("cve_total", len(it["vulnerabilities"]))
                cvss, ex = R.cvss_text(vulns, total), R.exploitation_text(vulns, total, published)
                self.assertTrue(front.startswith(cvss) and r["cvss"].startswith(cvss))
                self.assertIn(ex, front)
                self.assertIn(ex, r["exploitation"])
                listed = R.kev_listed(vulns)
                if listed:
                    short = R.kev_short(listed, published)  # "KEV 10/6" 또는 "KEV 2건"
                    self.assertIn(short.replace("KEV ", "KEV 등재 "), back)
                    self.assertTrue(r["target_note"].endswith(short) and r["exploitation"].endswith(short))

    # 3. KEV 기한 경과
    def test_p3_overdue_mark(self):
        self.assertEqual(row(BASE, A)["deadline_note"], "KEV 기한 10/9 경과")   # 10/9 < 발행 10/12
        self.assertEqual(row(BASE, B)["deadline_note"], "KEV 기한 10/31")       # 발행일 뒤
        data = fresh()
        data["items"][A]["vulnerabilities"][0]["kev"]["due"] = "2026-10-12"    # 발행일 당일은 경과 아님
        self.assertEqual(row(data, A)["deadline_note"], "KEV 기한 10/12")

    # 4. 악용 확인 + KEV 없음(근거 벤더)
    def test_p4_vendor_confirmed_without_kev(self):
        self.assertEqual(row(BASE, D)["exploitation_notes"], ["벤더 확인"])

    # 5. 새 호의 표 구조
    def test_p5_new_issue_top_level_priority_fails(self):
        data = fresh()
        data["priority"] = [{"target": "x", "vuln": "x", "severity": "긴급", "cvss": "x", "exploitation": "x", "deadline": "x"}]
        self.assertFails(data, "새 호는 최상위 priority[]를 쓰지 않음")

    def test_p5_new_issue_item_without_priority_fails(self):
        data = fresh()
        del data["items"][A]["priority"]
        self.assertFails(data, "$.items[0].priority: 필수 칸 없음")

    # 6. deadline_note
    def test_p6_deadline_note_with_facts_fails(self):
        for note in ("2주 내", "KEV 참고", "kisa 공지 후", "#1 우선", "３일"):
            with self.subTest(note=note):
                data = fresh()
                data["items"][E]["priority"]["deadline_note"] = note
                self.assertFails(data, "priority.deadline_note에는 숫자·CVE·KEV·KISA·#를 쓸 수 없음")

    def test_p6_deadline_note_on_kev_item_fails(self):
        data = fresh()
        data["items"][A]["priority"]["deadline_note"] = "해당 시"
        self.assertFails(data, "KEV 등재 항목에는 priority.deadline_note를 쓸 수 없음")

    # 7. 이전된 호
    def check_0928(self, change) -> list[str]:
        data = json.loads((REPO / "content/kisa-cert/2026-09-28.json").read_text(encoding="utf-8"))
        change(data)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "content/kisa-cert").mkdir(parents=True)
            (root / "docs/kisa-cert").mkdir(parents=True)
            path = root / "content/kisa-cert/2026-09-28.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            html = (REPO / "docs/kisa-cert/kisa_weekly_2026-09-28_public.html").read_bytes()
            (root / "docs/kisa-cert/kisa_weekly_2026-09-28_public.html").write_bytes(html)
            return V.check_issue(root, path, SCHEMA)

    def test_p7_migrated_issue_needs_priority(self):
        self.assertEqual(self.check_0928(lambda d: None), [])
        errs = self.check_0928(lambda d: d.pop("priority"))
        self.assertTrue(any("이전된 호는 2. 우선순위 표를 priority[]로 적어야 함" in e for e in errs), errs)

    def test_p7_migrated_item_priority_fails(self):
        errs = self.check_0928(lambda d: d["items"][0].update(priority={"target": "x", "details": ["x"], "deadline": "x"}))
        self.assertTrue(any("이전된 호에는 구조화 칸" in e for e in errs), errs)

    # 8. schema를 통과한 데이터에는 예외 없이 실패 목록
    def test_p8_no_exception_on_schema_valid_oddities(self):
        data = fresh()  # 글자 머리 줄 + 구조화 칸, priority 없음 → schema는 글자 쪽으로 통과
        it = data["items"][A]
        it["meta"], it["meta_refs"] = "CVSS 9.8", "KISA #9001"
        del it["priority"]
        self.assertEqual(V.schema_errors(data, SCHEMA, SCHEMA), [])
        errs = V.check_new_issue(data)
        self.assertTrue(any("priority(2. 우선순위 표 한 줄" in e for e in errs), errs)
        data = fresh()  # 글자 머리 줄 + priority만, 구조화 칸 없음
        it = data["items"][A]
        it["meta"], it["meta_refs"] = "CVSS 9.8", "KISA #9001"
        for k in ("vulnerabilities", "notices"):
            del it[k]
        self.assertEqual(V.schema_errors(data, SCHEMA, SCHEMA), [])
        self.assertTrue(V.check_new_issue(data))

    # 9. KEV 여러 건(등재일 다름), 벤더·KISA 근거 섞임
    def test_p9_kev_multiple_dates_shows_count(self):
        r = row(BASE, C)
        self.assertTrue(r["target_note"].endswith("KEV 2건"), r)
        self.assertTrue(r["exploitation"].endswith("· KEV 2건"), r)

    def test_p9_vendor_and_kisa_basis_without_kev(self):
        data = fresh()
        for v in data["items"][C]["vulnerabilities"]:  # 근거: vendor-c(vendor), kisa(kisa)
            v["kev"] = {"state": "not_listed"}
        self.assertEqual(errors(data), [])
        r = row(data, C)
        self.assertEqual((r["exploitation"], r["exploitation_notes"]), ("● 2건 악용 확인", ["벤더·KISA 확인"]))
        self.assertEqual(r["target_note"], "KISA #9003")
        data["items"][C]["vulnerabilities"][0]["exploitation"]["src"] = "kisa"
        self.assertEqual(row(data, C)["exploitation_notes"], ["KISA 확인"])


if __name__ == "__main__":
    unittest.main()
