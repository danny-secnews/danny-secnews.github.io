"""
KISA 새 호 PR 범위 검사(tools/kisa/pr_scope.py) 시험 — 표준 라이브러리만, 네트워크 없음.

  python -m unittest discover -s tools/kisa/tests -v

판정 함수 judge()는 직접 부르고, 입력 읽기(한 줄에 JSON 문자열 하나)는 실제로 프로그램을 실행해 표준 입력으로 확인한다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "tools" / "kisa"))
import pr_scope as S  # noqa: E402

DATA = "content/kisa-cert/2026-10-05.json"
HTML = "docs/kisa-cert/kisa_weekly_2026-10-05_public.html"


def encode(paths: list[str]) -> bytes:
    """workflow가 넘기는 모양: 경로마다 JSON 문자열 한 줄(UTF-8 그대로)."""
    return "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in paths).encode("utf-8")


def run(stdin: bytes) -> tuple[int, str]:
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"}
    p = subprocess.run([sys.executable, str(REPO / "tools/kisa/pr_scope.py")], input=stdin, capture_output=True, env=env)
    return p.returncode, p.stdout.decode("utf-8")


class Judge(unittest.TestCase):
    def assertPass(self, paths, applies):
        v = S.judge(paths)
        self.assertTrue(v.ok, v)
        self.assertEqual(v.applies, applies, v)

    def assertFail(self, paths, outside=None):
        v = S.judge(paths)
        self.assertFalse(v.ok, v)
        if outside is not None:
            self.assertEqual(v.outside, sorted(outside), v)

    def test_01_content_and_docs_only(self):
        self.assertPass([DATA, HTML], applies=True)

    def test_02_tools_only_not_applicable(self):
        self.assertPass(["tools/kisa/render.py", "tools/kisa/validate.py"], applies=False)

    def test_03_tools_and_docs_not_applicable(self):  # 렌더러를 고치고 HTML을 다시 만든 PR
        self.assertPass(["tools/kisa/render.py", "docs/kisa-cert/kisa_weekly_2026-09-28_public.html"], applies=False)

    def test_04_content_and_tools(self):
        self.assertFail([DATA, HTML, "tools/kisa/validate.py"], outside=["tools/kisa/validate.py"])

    def test_05_content_and_templates(self):
        self.assertFail([DATA, "templates/kisa-cert/page.html"], outside=["templates/kisa-cert/page.html"])

    def test_06_content_and_workflows(self):
        self.assertFail([DATA, ".github/workflows/kisa-validate.yml"], outside=[".github/workflows/kisa-validate.yml"])

    def test_07_content_and_other_files(self):
        self.assertFail([DATA, "docs/assets/site-nav.js", "README.md"], outside=["README.md", "docs/assets/site-nav.js"])
        self.assertFail([DATA, "docs/data/manifest.json"], outside=["docs/data/manifest.json"])
        self.assertFail([DATA, "content/kisa-certificate/x.json"], outside=["content/kisa-certificate/x.json"])

    def test_08_renames_count_both_paths(self):
        # content 파일을 범위 밖으로 이름 바꿈: 옛 경로(content)가 대상으로 만들고, 새 경로가 범위 밖
        self.assertFail(["tools/kisa/2026-10-05.json", DATA], outside=["tools/kisa/2026-10-05.json"])
        # 범위 밖 파일을 content로 이름 바꿈: 새 경로(content)가 대상으로 만들고, 옛 경로가 범위 밖
        self.assertFail([DATA, "tools/kisa/x.json"], outside=["tools/kisa/x.json"])

    def test_09_abnormal_paths_fail(self):
        for p in ("./content/kisa-cert/x.json", "content/kisa-cert/../../tools/x", "content\\kisa-cert\\x.json",
                  "/content/kisa-cert/x.json", "C:/repo/content/kisa-cert/x.json", "content//kisa-cert/x.json",
                  "content/kisa-cert/", ""):
            with self.subTest(path=p):
                v = S.judge([p])
                self.assertFalse(v.ok, v)
                self.assertTrue(v.bad, v)
        v = S.judge(["tools/x.py", "docs/./x"])  # 대상이 아닌 PR이어도 비정상 경로면 실패
        self.assertFalse(v.ok)

    def test_10_empty_list_passes(self):
        self.assertPass([], applies=False)


class StdinInput(unittest.TestCase):
    def test_cli_pass_and_fail_messages(self):
        code, out = run(encode([DATA, HTML]))
        self.assertEqual(code, 0, out)
        code, out = run(encode(["tools/kisa/render.py"]))
        self.assertEqual(code, 0, out)
        self.assertIn("대상 아님", out)
        code, out = run(encode([DATA, "tools/kisa/validate.py", "README.md"]))
        self.assertEqual(code, 1, out)
        self.assertIn(S.SCOPE_MSG, out)
        self.assertIn('"tools/kisa/validate.py"', out)
        self.assertIn('"README.md"', out)
        code, out = run(b"")  # 빈 입력 = 빈 목록 → 통과(대상 아님)
        self.assertEqual(code, 0, out)
        self.assertIn("대상 아님", out)

    def test_11_odd_names_stay_one_name(self):
        tricky = [
            "content/kisa-cert/a b.json",                       # 공백
            'docs/kisa-cert/x"\n"tools/evil.py',                # 따옴표·줄바꿈 — docs 아래 이름 하나
            "docs/kisa-cert/y\u2028tools/z.py",                 # 유니코드 줄 구분 문자 — 이름 하나
        ]
        self.assertEqual(S.read_paths(encode(tricky)), tricky)
        code, out = run(encode(tricky))
        self.assertEqual(code, 0, out)  # 셋 다 content·docs 아래의 이름 하나씩
        # 줄바꿈으로 범위 안 이름을 이어 붙여도 이름 전체가 tools/로 시작하면 범위 밖
        sneaky = [DATA, "tools/x.py\ncontent/kisa-cert/y.json"]
        self.assertEqual(len(S.read_paths(encode(sneaky))), 2)
        code, out = run(encode(sneaky))
        self.assertEqual(code, 1, out)
        self.assertIn(json.dumps("tools/x.py\ncontent/kisa-cert/y.json", ensure_ascii=False), out)

    def test_12_non_json_string_lines_fail(self):
        for raw in (b"content/kisa-cert/x.json\n",                     # 따옴표 없는 글자
                    b'"content/kisa-cert/x.json"\n123\n',              # JSON 숫자
                    b'["content/kisa-cert/x.json"]\n',                 # JSON 배열
                    b'"content/kisa-cert/x.json"\n\n"docs/kisa-cert/y.html"\n',  # 중간의 빈 줄
                    b'"content/kisa-cert/\xff.json"\n'):               # UTF-8 아님
            with self.subTest(raw=raw):
                with self.assertRaises(S.InputError):
                    S.read_paths(raw)
                code, out = run(raw)
                self.assertEqual(code, 1, out)
                self.assertIn("입력 오류", out)


if __name__ == "__main__":
    unittest.main()
