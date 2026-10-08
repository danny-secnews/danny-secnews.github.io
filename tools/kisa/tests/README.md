# tools/kisa/tests — 새 호(구조화 칸) 시험

```bash
python -m unittest discover -s tools/kisa/tests -v
```

**`fixtures/`의 데이터는 시험용 가상 데이터이며 실제 취약점·공지와 무관하다.**
벤더·제품 이름("예시 벤더 A", "Example Gateway A" 등), CVE 번호(CVE-2026-999xxxx),
KISA 공지 번호(#9001~), 출처 주소(`*.example`, 가상 게시물 번호)는 모두 지어낸 값이다.
사이트에 게시하지 않으며 content/·docs/에 두지 않는다.

시험 이름의 "Cisco 형", "Citrix 형" 같은 표현은 실제 호에서 본 머리 줄 **유형**을 가리킬 뿐, 그 벤더의 데이터가 아니다.
외부 네트워크를 쓰지 않는다. 일부 시험은 시스템 임시 폴더에 파일을 만들고 끝나면 지운다(저장소 폴더에는 쓰지 않음).
