# tools/kisa — KISA 보안공지 주간 리포트 도구

주간 리포트는 **호별 데이터(JSON)를 고정 틀에 넣어 HTML을 만드는** 방식으로 관리한다.
표준 라이브러리만 쓴다.

| 경로 | 역할 |
|---|---|
| `content/kisa-cert/<week_start>.json` | 호별 데이터(단일 기준). 사이트에는 공개되지 않는다 |
| `templates/kisa-cert/page.html` | 고정 틀 |
| `tools/kisa/schema.json` | 데이터 형식(필수 칸·형식의 유일한 정의) |
| `docs/kisa-cert/kisa_weekly_<week_start>_public.html` | 렌더 결과(게시본) |

## 원칙

**HTML을 직접 고치지 않는다.** 데이터를 고치고 다시 렌더링한다.
틀이나 렌더러를 고치면 데이터로 만든 호를 모두 다시 렌더링해 함께 올린다.
검사기는 HTML이 데이터 렌더 결과와 다르면 실패한다.

## 실행

```bash
python tools/kisa/render.py 2026-09-28     # 한 호 렌더링 (--all: 전부, --stdout: 저장 없이 출력)
python tools/kisa/validate.py              # 전부 검사 (주차를 주면 그 호만, --root DIR: 다른 작업 트리)
python tools/kisa/compare_html.py git:origin/main:docs/kisa-cert/X.html docs/kisa-cert/X.html
```

- `render.py`: 데이터 → HTML. UTF-8·LF로 쓰고, `portal-date` 메타와 상단 바 줄을 넣는다.
  본문 글자는 `**굵게**`, `` `코드` ``, `[미확인]`(회색), 줄바꿈만 해석하고 나머지는 모두 이스케이프한다.
- `validate.py`: 형식(schema.json), 날짜, 이전된 호 면제, 렌더 일치, HTML 필수 요소, 폴더 검사.
  PR에서는 `.github/workflows/kisa-validate.yml`이 실행한다. 종료코드 0 통과 / 1 실패.
- `compare_html.py`: 옛 HTML과 새 HTML의 화면 글자·토큰(CVE·버전·숫자·[미확인])·문장·꾸밈 비교.
  게시본을 데이터로 옮긴 뒤 정보가 빠지지 않았는지 확인할 때 쓴다. 종료코드 0 같음 / 1 다름.

## 고정 목록 두 개 (`validate.py`)

- **`MIGRATED_WEEKS`** — 기존 게시본을 데이터로 옮긴 주차. 이 주차들에만 옮긴 글자 그대로의 항목 머리 줄,
  빈 출처 URL, 근거 없음, 고정 안내문 바꿔 쓰기(`boilerplate`)가 허용된다.
  옛 게시본을 데이터로 옮길 때만 추가한다. 새로 만드는 호는 넣지 않는다.
  데이터의 `provenance.type: "migrated"` 표시와 이 목록이 둘 다 맞아야 면제된다.
- **`LEGACY_HTML`** — 데이터 없이 남아 있는 옛 HTML(손으로 만든 게시본과 안내 페이지).
  `docs/kisa-cert/`의 HTML은 이 목록에 있거나 데이터에서 만든 것이어야 한다.
  손으로 만든 HTML을 새로 올릴 때 추가하고, 그 호를 데이터로 옮기면 뺀다.

목록에 없는 주차의 새 데이터는 아직 검사기가 지원하지 않아 실패한다(새 호 자동 생성은 준비 중).

## 과도기 절차 (새 호 자동 생성이 준비될 때까지)

주간 리포트는 기존 방식대로 HTML로 만든다. 다만 **웹 업로드로 main에 바로 올리지 않는다.**

1. 최신 main에서 브랜치를 만든다.
2. HTML을 `docs/kisa-cert/kisa_weekly_<대상 주간 시작일>_public.html`로 넣는다.
   머리말의 `대상 기간: … | 발행: …` 줄을 지켜야 목록 날짜가 맞게 나온다.
3. 같은 변경에서 `validate.py`의 `LEGACY_HTML`에 그 파일 이름을 추가한다.
4. `python tools/kisa/validate.py`가 통과하는지, `python tools/build_manifest.py --check`에
   `주의:` 경고(발행일을 못 읽음, 같은 주차 중복 등)가 없는지 확인한 뒤 PR로 올린다.
   이때 `필요: 목록 갱신`은 정상이다 — 목록(manifest)은 병합 후 portal-manifest 워크플로가 갱신하므로
   PR에 넣지 않는다.
