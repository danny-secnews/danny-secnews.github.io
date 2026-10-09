"""
KEV 대조 도구(tools/kisa/kev_check.py) 시험 — 표준 라이브러리만, 네트워크 없음.

  python -m unittest discover -s tools/kisa/tests -v

가짜 목록 fixtures/kev_catalog.json(7건)과 가상 호 fixtures/new_issue.json을 쓴다.
new_issue.json의 checks.kev(catalog_version·count)는 파일을 고치지 않고 메모리에서 가짜 목록에 맞춘다.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "tools" / "kisa"))
import kev_check as K  # noqa: E402

CAT = json.loads((HERE / "fixtures" / "kev_catalog.json").read_text(encoding="utf-8"))
ISSUE = json.loads((HERE / "fixtures" / "new_issue.json").read_text(encoding="utf-8"))
A, B, C, D, E = range(5)


def catalog(**changes) -> dict:
    c = copy.deepcopy(CAT)
    c.update(changes)
    return c


def issue(cat: dict | None = None) -> dict:
    """가상 새 호를 복제해 checks.kev를 목록의 판·건수에 맞춘다(파일은 고치지 않음)."""
    d = copy.deepcopy(ISSUE)
    cat = cat or CAT
    d["checks"]["kev"].update(catalog_version=cat["catalogVersion"], count=cat["count"])
    return d


def legacy_0928() -> dict:
    return json.loads((REPO / "content/kisa-cert/2026-09-28.json").read_text(encoding="utf-8"))


def check(data: dict, cat: dict | bytes) -> tuple[int, str]:
    """새 임시 폴더에 호 데이터와 목록 파일을 두고 run_check를 부른다."""
    with tempfile.TemporaryDirectory(prefix="kisa-kev-") as tmp:
        root = Path(tmp)
        (root / "content/kisa-cert").mkdir(parents=True)
        (root / f"content/kisa-cert/{data['week_start']}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        cat_path = root / "kev.json"
        cat_path.write_bytes(cat if isinstance(cat, bytes) else json.dumps(cat, ensure_ascii=False).encode("utf-8"))
        code, lines = K.run_check(data["week_start"], cat_path, root)
    return code, "\n".join(lines)


def cli(*args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"}
    return subprocess.run([sys.executable, str(REPO / "tools/kisa/kev_check.py"), *args], capture_output=True, env=env)


def vuln(data: dict, item: int, n: int = 0) -> dict:
    return data["items"][item]["vulnerabilities"][n]


class NewIssue(unittest.TestCase):
    def test_k01_match_passes(self):
        code, out = check(issue(), CAT)
        self.assertEqual(code, 0, out)
        self.assertIn("불일치 없음", out)

    def test_k02_not_listed_but_in_catalog_fails(self):
        d = issue()
        vuln(d, A)["kev"] = {"state": "not_listed"}
        code, out = check(d, CAT)
        self.assertEqual(code, 1, out)
        self.assertIn("✗ 3-1 CVE-2026-9990001\n      호 데이터: KEV 미등재\n      KEV 목록:  KEV 등재 2026-10-06, 기한 2026-10-09", out)

    def test_k03_listed_but_missing_from_catalog_fails(self):
        cat = catalog(vulnerabilities=[v for v in CAT["vulnerabilities"] if v["cveID"] != "CVE-2026-9990001"], count=6)
        code, out = check(issue(cat), cat)
        self.assertEqual(code, 1, out)
        self.assertIn("호 데이터: KEV 등재 2026-10-06, 기한 2026-10-09\n      KEV 목록:  KEV 미등재", out)

    def test_k04_listed_with_different_dates_fails(self):
        for key, value in (("added", "2026-10-05"), ("due", "2026-10-30")):
            with self.subTest(key=key):
                d = issue()
                vuln(d, A)["kev"][key] = value
                code, out = check(d, CAT)
                self.assertEqual(code, 1, out)
                self.assertIn("✗ 3-1 CVE-2026-9990001", out)

    def test_k05_text_only_cve_in_catalog_fails_but_url_is_ignored(self):
        d = issue()
        d["items"][A]["sources"].append({"id": "nvd-z", "kind": "nvd", "viewed": True, "label": "NVD 기록",
                                         "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-9990099"})
        code, out = check(d, CAT)
        self.assertEqual(code, 0, out)  # 주소에만 든 CVE 번호는 찾지 않는다
        d["items"][A]["situation"].append("관련 취약점 CVE-2026-9990099도 함께 언급")
        code, out = check(d, CAT)
        self.assertEqual(code, 1, out)
        self.assertIn("✗ CVE-2026-9990099: 글에 나온 CVE가 KEV에 등재돼 있는데 구조화 칸에 없음", out)
        self.assertIn("화면 글: 3-1.situation[1]", out)

    def test_k06_other_catalog_version_or_count_is_input_error(self):
        d = issue()
        d["checks"]["kev"]["catalog_version"] = "2026.10.09"
        code, out = check(d, CAT)
        self.assertEqual(code, 2, out)
        self.assertIn("다른 판의 목록으로는 판정하지 않는다", out)
        d = issue()
        d["checks"]["kev"]["count"] = 8
        code, out = check(d, CAT)
        self.assertEqual(code, 2, out)

    def test_k08_new_in_period_but_not_in_issue_is_info_only(self):
        code, out = check(issue(), CAT)
        self.assertEqual(code, 0, out)
        self.assertIn("CVE-2026-9990099 | 등재 2026-10-07 | 기한 2026-10-28  ← 이번 호에 없는 기간 내 KEV 신규 등재(안내)", out)
        self.assertIn("CVE-2026-9990001 | 등재 2026-10-06 | 기한 2026-10-09\n", out)  # 호에 있는 것은 표시 없음
        self.assertNotIn("CVE-2025-9990050", out)  # 대상 주간 밖

    def test_k09_catalog_older_than_week_end_warns(self):
        cat = catalog(catalogVersion="2026.10.09")
        code, out = check(issue(cat), cat)
        self.assertIn("⚠ 경고: 이 판(2026-10-09)은 대상 기간 끝(2026-10-11)보다 이르다. 그 뒤의 등재는 이 대조로 확인되지 않는다.", out)


class CatalogErrors(unittest.TestCase):
    CASES = {
        "count와 길이 불일치": lambda c: c.update(count=6),
        "필수 칸 없음": lambda c: c["vulnerabilities"][0].pop("dueDate"),
        "cveID 중복": lambda c: (c["vulnerabilities"].append(dict(c["vulnerabilities"][0])), c.update(count=8)),
        "없는 날짜": lambda c: c["vulnerabilities"][0].update(dateAdded="2026-02-30"),
        "CVE 형식 오류": lambda c: c["vulnerabilities"][0].update(cveID="CVE-26-1"),
        "없는 날짜의 catalogVersion": lambda c: c.update(catalogVersion="2026.02.30"),
        "잘못된 dateReleased": lambda c: c.update(dateReleased="yesterday"),
        "count가 true": lambda c: c.update(count=True),
        "count가 음수": lambda c: c.update(count=-1),
        "vulnerabilities가 배열이 아님": lambda c: c.update(vulnerabilities={"x": 1}),
    }

    def test_k07_each_catalog_error_is_exit_2_without_traceback(self):
        for name, change in self.CASES.items():
            with self.subTest(name):
                cat = copy.deepcopy(CAT)
                change(cat)
                raw = json.dumps(cat, ensure_ascii=False).encode("utf-8")
                with self.assertRaises(K.CatalogError):
                    K.parse_catalog(raw)
                with tempfile.TemporaryDirectory(prefix="kisa-kev-bad-") as tmp:
                    p = Path(tmp) / "kev.json"
                    p.write_bytes(raw)
                    r = cli("check", "2026-09-28", "--catalog", str(p))
                out, err = r.stdout.decode("utf-8"), r.stderr.decode("utf-8", "replace")
                self.assertEqual(r.returncode, 2, out + err)
                self.assertIn("입력 오류: 목록 파일 형식", out)
                self.assertNotIn("Traceback", out + err)

    def test_missing_catalog_file_is_exit_2(self):
        with tempfile.TemporaryDirectory(prefix="kisa-kev-none-") as tmp:
            r = cli("check", "2026-09-28", "--catalog", str(Path(tmp) / "없음.json"))
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr.decode("utf-8", "replace"))


class Legacy(unittest.TestCase):
    def test_k10_legacy_issue_shows_table_and_exits_0(self):
        d = legacy_0928()
        d["items"][0]["meta_refs"] += " · CVE-2026-9990001"    # 글자 머리 줄에만
        d["priority"][0]["target_note"] += " · CVE-2026-9990011"  # 최상위 priority[]에만
        code, out = check(d, CAT)
        self.assertEqual(code, 0, out)
        self.assertIn("현재 받은 KEV 판(2026.10.10) 기준", out)
        self.assertIn("CVE-2026-9990001 | 등재 | 2026-10-06 | 2026-10-09 | 3-1.meta_refs", out)
        self.assertIn("CVE-2026-9990011 | 등재 | 2026-10-10 | 2026-10-31 | priority[0].target_note", out)
        self.assertIn("CVE-2026-88771 | 미등재 | - | - |", out)  # 가짜 목록에는 없음

    def test_k11_notes_footnotes_and_boilerplate_are_scanned(self):
        d = legacy_0928()
        d["overview_note"] += " CVE-2026-1111111"
        d["unverified_footnote"] += " CVE-2026-2222222"
        d["boilerplate"] = {"footer_notice": "안내 CVE-2026-3333333"}
        found = K.text_cves(d)
        self.assertEqual(found["CVE-2026-1111111"], ["overview_note"])
        self.assertEqual(found["CVE-2026-2222222"], ["unverified_footnote"])
        self.assertEqual(found["CVE-2026-3333333"], ["boilerplate.footer_notice"])

    def test_machine_fields_are_not_scanned(self):
        d = issue()
        d["provenance"]["source_html"] = "CVE-2026-4444444"
        d["checks"]["kev"]["url"] = "https://www.cisa.gov/CVE-2026-5555555"
        d["items"][A]["notices"]["vendor"]["advisories"][0]["id"] = "CVE-2026-6666666"
        found = K.text_cves(d)
        for cve in ("CVE-2026-4444444", "CVE-2026-5555555", "CVE-2026-6666666"):
            self.assertNotIn(cve, found)


class Abbreviated(unittest.TestCase):
    """줄여 쓴 CVE 번호(온전한 CVE 뒤 ·, 쉼표, /로 이어지는 숫자)."""

    def test_a1_new_issue_with_short_form_fails(self):
        d = issue()
        d["items"][A]["situation"].append("함께 고친 CVE-2026-9990001 · 9990012 확인")
        code, out = check(d, CAT)
        self.assertEqual(code, 1, out)
        self.assertIn("CVE 번호를 줄여 쓰지 않는다. 대조에서 빠질 수 있다", out)
        self.assertIn("3-1.situation[1]: 'CVE-2026-9990001 · 9990012' → CVE-2026-9990012", out)
        # 숫자 뒤에 조사가 바로 붙으면("9990012도") 규칙상 줄여 쓴 번호로 보지 않는다
        self.assertEqual(K.abbreviations("CVE-2026-9990001 · 9990012도 확인"), [])

    def test_a2_legacy_short_form_is_restored_into_table(self):
        d = legacy_0928()
        d["tracking"][0]["target_note"] = "CVE-2026-9990001 · 9990011"  # 9990011은 줄여 쓴 곳에만
        code, out = check(d, CAT)
        self.assertEqual(code, 0, out)
        self.assertIn("줄여 쓴 번호(추정) 위치", out)
        self.assertIn("CVE-2026-9990011 | 등재 | 2026-10-10 | 2026-10-31 | - | "
                      "tracking[0].target_note 'CVE-2026-9990001 · 9990011'", out)

    def test_a2_short_place_shown_even_if_full_number_appears_elsewhere(self):
        d = legacy_0928()
        d["tracking"][0]["target_note"] = "CVE-2026-9990001 · 9990011"
        d["overview"][0] += " CVE-2026-9990011"  # 다른 곳에 온전한 번호도 있음
        code, out = check(d, CAT)
        self.assertIn("CVE-2026-9990011 | 등재 | 2026-10-10 | 2026-10-31 | overview[0] | "
                      "tracking[0].target_note 'CVE-2026-9990001 · 9990011'", out)

    def test_a3_chain_of_two_or_more(self):
        self.assertEqual([c for c, _ in K.abbreviations("CVE-2026-88771 · 88772 · 88773")],
                         ["CVE-2026-88772", "CVE-2026-88773"])
        self.assertEqual([c for c, _ in K.abbreviations("CVE-2025-1111, 2222 / 3333")],
                         ["CVE-2025-2222", "CVE-2025-3333"])

    def test_a4_markdown_emphasis_allowed(self):
        self.assertEqual([c for c, _ in K.abbreviations("**CVE-2026-93616** · **85102** 확인")], ["CVE-2026-85102"])
        self.assertEqual([c for c, _ in K.abbreviations("CVE-2026-93616 · **85102**")], ["CVE-2026-85102"])

    def test_a5_dates_versions_builds_and_words_are_not_short_forms(self):
        for text in ("CVE-2026-1234 · 2026-10-01",       # 날짜(뒤에 -)
                     "CVE-2026-1234 / 2026.10.01",       # 날짜(뒤에 .)
                     "CVE-2026-1234, 9.0.122",           # 버전(짧은 숫자)
                     "CVE-2026-1234 / 1234.5",           # 버전(뒤에 .)
                     "CVE-2026-1234 / 14.1-73.37",       # 빌드
                     "CVE-2026-1234 · 1739건",           # 숫자 뒤 한글
                     "CVE-2026-1234, 2026년",            # 숫자 뒤 한글
                     "CVE-2026-1234 · 12345abc",         # 숫자 뒤 영문
                     "CVE-2026-1234 · 5678/9",           # 숫자 뒤 /
                     "CVE-2026-1234 외 5678",            # 일반 단어
                     "CVE-2026-1234 · 및 5678",          # 구분 기호 뒤 단어
                     "CVE-2026-48411~48416"):            # 범위(물결)
            with self.subTest(text=text):
                self.assertEqual(K.abbreviations(text), [])

    def test_a6_real_0928_patterns(self):
        found = K.short_cves(legacy_0928())
        self.assertEqual(found["CVE-2026-88772"], [("tracking[0].target_note", "CVE-2026-88771 · 88772")])
        self.assertEqual(found["CVE-2026-85102"], [("tracking[2].target_note", "CVE-2026-93616 · 85102")])


class Download(unittest.TestCase):
    def test_k12_only_two_allowed_addresses(self):
        self.assertEqual(K.SOURCES, {
            "cisa": "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
            "mirror": "https://raw.githubusercontent.com/cisagov/kev-data/main/known_exploited_vulnerabilities.json"})
        self.assertNotIn("develop", (REPO / "tools/kisa/kev_check.py").read_text(encoding="utf-8").split('"""', 2)[2])

    def test_k12_existing_out_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(prefix="kisa-kev-dl-") as tmp:
            out = Path(tmp) / "kev-2026.10.10.json"
            out.write_text("기존 증거 파일", encoding="utf-8")
            with mock.patch.object(K, "urlopen") as fake, contextlib.redirect_stdout(io.StringIO()) as buf:
                code = K.download(out, "mirror")
            self.assertEqual(code, 2)
            fake.assert_not_called()  # 받기 전에 멈춘다
            self.assertEqual(out.read_text(encoding="utf-8"), "기존 증거 파일")
            self.assertIn("덮어쓰지 않는다", buf.getvalue())

    def test_cisa_failure_does_not_fall_back_to_mirror(self):
        err = urllib.error.HTTPError(K.SOURCES["cisa"], 403, "Forbidden", {}, io.BytesIO(b""))
        with tempfile.TemporaryDirectory(prefix="kisa-kev-dl-") as tmp:
            out = Path(tmp) / "kev.json"
            with mock.patch.object(K, "urlopen", side_effect=err) as fake, contextlib.redirect_stdout(io.StringIO()) as buf:
                code = K.download(out, "cisa")
            self.assertEqual(code, 1)
            self.assertEqual([c.args[0] for c in fake.call_args_list], [K.SOURCES["cisa"]])  # mirror로 넘어가지 않음
            self.assertFalse(out.exists())
            self.assertIn("--catalog", buf.getvalue())
            self.assertIn("--source mirror", buf.getvalue())

    def test_invalid_download_leaves_no_file_and_valid_one_reports_age(self):
        with tempfile.TemporaryDirectory(prefix="kisa-kev-dl-") as tmp:
            bad, good = Path(tmp) / "bad.json", Path(tmp) / "kev-2026.10.10.json"
            with mock.patch.object(K, "urlopen", return_value=io.BytesIO(b'{"catalogVersion": "x"}')), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(K.download(bad, "mirror"), 1)
            self.assertFalse(bad.exists())
            raw = (HERE / "fixtures" / "kev_catalog.json").read_bytes()
            with mock.patch.object(K, "urlopen", return_value=io.BytesIO(raw)), contextlib.redirect_stdout(io.StringIO()) as buf:
                self.assertEqual(K.download(good, "mirror", today=date(2026, 10, 20)), 0)
            self.assertEqual(good.read_bytes(), raw)
            text = buf.getvalue()
            self.assertIn("판 2026.10.10 · 7건", text)
            self.assertIn("10일 전 판", text)
            self.assertIn("최신이 아닐 수 있음", text)


if __name__ == "__main__":
    unittest.main()
