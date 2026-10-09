# tools/kisa/tests — 새 호(구조화 칸) 시험

```bash
python -m unittest discover -s tools/kisa/tests -v
```

PR 검사(`.github/workflows/kisa-validate.yml`)가 `validate.py`와 이 시험 전체를 실행한다.

- `test_structured.py` — 새 호 구조화 칸의 규칙·머리 줄·우선순위 표, 09-28 렌더 바이트 일치,
  가상 새 호가 실제 `validate.py` 흐름을 통과·실패하는지(관문 개방 후).
- `test_pr_scope.py` — 새 호 PR 범위 판정(`pr_scope.py`): 허용 범위, 이름 바꾸기, 비정상 경로, JSON 한 줄 입력.
- `test_negative.py` — 일부러 틀린 데이터·HTML 14가지가 `validate.py`에서 기대대로 실패(또는 통과)하는지.
  09-28 호를 임시 폴더에 복사해 한 곳씩 바꿔 검사한다.

**`fixtures/`의 데이터는 시험용 가상 데이터이며 실제 취약점·공지와 무관하다.**
벤더·제품 이름("예시 벤더 A", "Example Gateway A" 등), CVE 번호(CVE-2026-999xxxx),
KISA 공지 번호(#9001~), 출처 주소(`*.example`, 가상 게시물 번호)는 모두 지어낸 값이다.
사이트에 게시하지 않으며 content/·docs/에 두지 않는다.

시험 이름의 "Cisco 형", "Citrix 형" 같은 표현은 실제 호에서 본 머리 줄 **유형**을 가리킬 뿐, 그 벤더의 데이터가 아니다.
외부 네트워크를 쓰지 않는다. 일부 시험은 시스템 임시 폴더에 파일을 만들고 끝나면 지운다(저장소 폴더에는 쓰지 않음).
