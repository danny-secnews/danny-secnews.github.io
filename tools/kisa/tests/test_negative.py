"""
KISA 검사기 실패 시험 — 일부러 틀린 데이터·HTML이 validate.py에서 실패하는지(그리고 정상은 통과하는지) 본다.
STEP 3B 때 저장소 밖에서 쓰던 14가지 경우를 그대로 옮겼다. 표준 라이브러리만, 네트워크 없음.

  python -m unittest discover -s tools/kisa/tests -v

경우마다 새 임시 폴더(tempfile)에 content/kisa-cert·docs/kisa-cert를 복사해 한 곳을 바꾸고,
validate.py --root 로 검사한다. 저장소 파일은 고치지 않는다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "tools" / "kisa"))
import render as R  # noqa: E402

H = "docs/kisa-cert/kisa_weekly_2026-09-28_public.html"
J = "content/kisa-cert/2026-09-28.json"


def jload(root: Path, rel: str = J) -> dict:
    return json.loads((root / rel).read_text(encoding="utf-8"))


def jsave(root: Path, data: dict, rel: str) -> None:
    (root / rel).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def new_week(root: Path, week: str, published: str, ptype: str) -> None:
    """09-28 데이터를 복제해 다른 주차의 데이터와 그 렌더 HTML을 만든다."""
    d = jload(root)
    d["week_start"], d["id"], d["published_date"] = week, f"kisa-weekly-{week}", published
    d["provenance"] = {"type": ptype}
    if ptype == "migrated":
        d["provenance"].update(source_html=f"docs/kisa-cert/kisa_weekly_{week}_public.html", source_commit="x")
    rel = f"content/kisa-cert/{week}.json"
    jsave(root, d, rel)
    (root / "docs/kisa-cert" / R.out_name(week)).write_text(R.render(d, rel), encoding="utf-8", newline="\n")


def edit_html(root: Path, old: str, new: str) -> None:
    p = root / H
    s = p.read_text(encoding="utf-8")
    assert old in s, f"바꿀 글자가 HTML에 없음: {old!r}"
    p.write_text(s.replace(old, new, 1), encoding="utf-8", newline="\n")


def edit_json(root: Path, change) -> None:
    d = jload(root)
    change(d)
    jsave(root, d, J)


def to_crlf(path: Path) -> None:
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))


# (이름, 기대, 데이터를 바꾸는 함수). 기대: "통과" / "실패" / "실패(아직 지원하지 않음)"
CASES = [
    ("정상 데이터(09-28) 그대로", "통과", lambda r: None),
    ("HTML을 한 글자 직접 고침", "실패", lambda r: edit_html(r, "7건(#2549~#2555)", "8건(#2549~#2555)")),
    ("필수 칸(published_date) 삭제", "실패", lambda r: edit_json(r, lambda d: d.pop("published_date"))),
    ("필수 칸(items[0].remediation) 삭제", "실패", lambda r: edit_json(r, lambda d: d["items"][0].pop("remediation"))),
    ("목록에 없는 주차(2026-10-05)가 migrated 표시", "실패", lambda r: new_week(r, "2026-10-05", "2026-10-12", "migrated")),
    ("목록에 없는 주차(2026-10-05)의 일반 데이터", "실패(아직 지원하지 않음)",
     lambda r: new_week(r, "2026-10-05", "2026-10-12", "generated")),
    ("면제 목록 주차인데 provenance를 generated로 바꿈", "실패",
     lambda r: edit_json(r, lambda d: d.update(provenance={"type": "generated"}))),
    ("HTML 줄바꿈만 CRLF로 바꿈", "통과", lambda r: to_crlf(r / H)),
    ("데이터(JSON) 줄바꿈만 CRLF로 바꿈", "통과", lambda r: to_crlf(r / J)),
    ("같은 주차 HTML을 다른 이름으로 하나 더 올림", "실패",
     lambda r: shutil.copy(r / H, r / "docs/kisa-cert/kisa_weekly_2026-09-28_public_v2.html")),
    ("HTML 파일을 지움", "실패", lambda r: (r / H).unlink()),
    ("본문 표기 오류(닫히지 않은 **)", "실패",
     lambda r: edit_json(r, lambda d: d["overview"].__setitem__(0, d["overview"][0] + " **열림"))),
    ("published_date가 대상 주간 안(2026-10-01)", "실패",
     lambda r: edit_json(r, lambda d: d.update(published_date="2026-10-01"))),
    ("정의되지 않은 칸 추가(html)", "실패", lambda r: edit_json(r, lambda d: d.update(html="<p>직접 쓴 HTML</p>"))),
]


def run_case(change) -> tuple[int, str]:
    """새 임시 폴더에 복사본을 만들어 바꾼 뒤 validate.py를 돌린다. (종료코드, 출력)을 돌려준다."""
    with tempfile.TemporaryDirectory(prefix="kisa-neg-") as tmp:
        root = Path(tmp)
        for sub in ("content/kisa-cert", "docs/kisa-cert"):
            shutil.copytree(REPO / sub, root / sub)
        change(root)
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"}  # 출력 형식을 CI·로컬에서 같게
        p = subprocess.run([sys.executable, str(REPO / "tools/kisa/validate.py"), "--root", str(root)],
                           capture_output=True, env=env)
    return p.returncode, p.stdout.decode("utf-8")


assert len(CASES) == 14, "옮겨 온 경우는 14가지여야 함 — 빼거나 합치지 않는다"


class NegativeCases(unittest.TestCase):
    """경우마다 test_00 ~ test_13. 시험 설명(-v 출력)에 경우 이름과 기대 결과가 나온다."""


def _make(name: str, expect: str, change):
    def test(self):
        code, out = run_case(change)
        self.assertIn(code, (0, 1), out)  # 판정(통과·실패)이어야 하고 검사기 자체 오류면 안 됨
        self.assertEqual("통과" if code == 0 else "실패", expect.split("(")[0], out)
        if "아직" in expect:
            self.assertIn("아직 지원하지 않음", out)
    test.__doc__ = f"{name} → {expect}"
    return test


for _i, (_name, _expect, _change) in enumerate(CASES):
    setattr(NegativeCases, f"test_{_i:02d}", _make(_name, _expect, _change))


if __name__ == "__main__":
    unittest.main()
