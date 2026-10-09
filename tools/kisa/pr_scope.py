#!/usr/bin/env python3
"""
KISA 새 호 PR 범위 검사 — 표준 라이브러리만 사용.

main에 있는 .github/workflows/kisa-pr-scope.yml(pull_request_target)이 main 쪽의 이 파일을 실행한다.
PR 쪽 코드는 받지도 실행하지도 않고, PR이 바꾼 파일 이름 목록만 읽는다.

  (파일 이름 목록) | python tools/kisa/pr_scope.py

입력: 표준 입력, 한 줄에 하나씩 JSON 문자열로 인코딩한 경로(PR 파일의 filename과 previous_filename).
      JSON 문자열이 아닌 줄이 있으면 실패한다. 줄은 '\\n'으로만 나눈다.
규칙: content/kisa-cert/ 아래 파일을 하나라도 바꾼 PR(추가·수정·삭제·이름 바꾸기의 옛 경로와 새 경로)은
      바꾼 모든 파일이 content/kisa-cert/ 또는 docs/kisa-cert/ 아래여야 한다.
      content/kisa-cert/를 바꾸지 않은 PR은 대상이 아니다(통과).
      비정상 경로(빈 경로, 절대 경로, '\\' 포함, '.'·'..'·빈 요소)가 하나라도 있으면 대상 여부와 관계없이 실패한다.
      경로를 정규화해서 받아 주지 않는다.
종료코드 0 통과(대상 아님 포함) / 1 실패
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field

TRIGGER = "content/kisa-cert/"
ALLOWED = ("content/kisa-cert/", "docs/kisa-cert/")
SCOPE_MSG = "새 호 PR 에는 content/kisa-cert/ 와 docs/kisa-cert/ 파일만 넣는다"
DRIVE = re.compile(r"^[A-Za-z]:")


class InputError(ValueError):
    pass


@dataclass
class Verdict:
    ok: bool
    applies: bool
    bad: list[tuple[str, str]] = field(default_factory=list)   # (경로, 이유)
    outside: list[str] = field(default_factory=list)           # 범위 밖 파일


def path_problem(path: str) -> str | None:
    """비정상 경로면 이유, 정상이면 None. 정규화하지 않고 그대로 판정한다."""
    if not path:
        return "빈 경로"
    if "\\" in path:
        return "'\\' 포함"
    if path.startswith("/") or DRIVE.match(path):
        return "절대 경로"
    if any(part in ("", ".", "..") for part in path.split("/")):
        return "'.'·'..'·빈 요소 포함"
    return None


def judge(paths: list[str]) -> Verdict:
    """PR이 바꾼 파일 경로들(이름 바꾸기는 옛 경로와 새 경로 모두)을 판정한다. 순수 함수."""
    bad = [(p, why) for p in paths if (why := path_problem(p))]
    if bad:
        return Verdict(ok=False, applies=any(p.startswith(TRIGGER) for p in paths), bad=bad)
    if not any(p.startswith(TRIGGER) for p in paths):
        return Verdict(ok=True, applies=False)
    outside = sorted({p for p in paths if not p.startswith(ALLOWED)})
    return Verdict(ok=not outside, applies=True, outside=outside)


def read_paths(raw: bytes) -> list[str]:
    """표준 입력 바이트 → 경로 목록. 한 줄에 JSON 문자열 하나. 마지막 줄바꿈 하나는 허용."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise InputError(f"입력이 UTF-8이 아님: {e}") from None
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    paths = []
    for n, line in enumerate(lines, 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            raise InputError(f"{n}번째 줄이 JSON이 아님: {line[:80]!r}") from None
        if not isinstance(value, str):
            raise InputError(f"{n}번째 줄이 JSON 문자열이 아님: {line[:80]!r}")
        paths.append(value)
    return paths


def show(path: str) -> str:
    return json.dumps(path, ensure_ascii=False)  # 줄바꿈 등이 든 이름도 한 줄로, 그대로 보이게


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    try:
        paths = read_paths(sys.stdin.buffer.read())
    except InputError as e:
        print(f"실패: 입력 오류 — {e}")
        return 1
    v = judge(paths)
    if v.bad:
        print(f"실패: 비정상 경로 {len(v.bad)}건 — 경로를 정규화해서 받아 주지 않음")
        for p, why in v.bad:
            print(f"  - {show(p)} ({why})")
        return 1
    if not v.applies:
        print(f"통과: 대상 아님 — content/kisa-cert/를 바꾸지 않은 PR (바뀐 경로 {len(paths)}건)")
        return 0
    if v.outside:
        print(f"실패: {SCOPE_MSG}. 범위 밖 파일 {len(v.outside)}건:")
        for p in v.outside:
            print(f"  - {show(p)}")
        return 1
    print(f"통과: 새 호 PR 범위 — 바뀐 경로 {len(paths)}건이 모두 content/kisa-cert/·docs/kisa-cert/ 아래")
    return 0


if __name__ == "__main__":
    sys.exit(main())
