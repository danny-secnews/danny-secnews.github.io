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
  종료코드 0 통과 / 1 실패.

**PR 검사** — `.github/workflows/kisa-validate.yml`이 KISA 경로가 바뀐 PR에서 `validate.py`와
시험 전체(`python -m unittest discover -s tools/kisa/tests -v`)를 실행한다. 둘 중 하나라도 실패하면 PR 검사는 실패다.
`validate.py`가 실패해도 시험은 이어서 실행되어 두 결과를 함께 볼 수 있다.

**새 호 PR 범위 검사** — `.github/workflows/kisa-pr-scope.yml`이 모든 PR에서 `tools/kisa/pr_scope.py`로 판정한다.

- 막는 것: 호 데이터(`content/kisa-cert/`)를 바꾸는 PR이 검사기·렌더러·틀·workflow 등을 함께 고쳐
  자기 검사를 스스로 느슨하게 만드는 것. `content/kisa-cert/`를 하나라도 바꾼(추가·수정·삭제·이름 바꾸기의 옛·새 경로) PR은
  바꾼 모든 파일이 `content/kisa-cert/` 또는 `docs/kisa-cert/` 아래여야 한다. 비정상 경로(절대 경로, `\`, `.`·`..`)는 실패.
- **main 쪽 코드로 돈다.** `pull_request_target`이라 main에 있는 workflow와 `pr_scope.py`가 실행되고,
  PR 쪽 코드는 받지도 실행하지도 않는다. PR에서 읽는 것은 바뀐 파일 이름 목록뿐이다.
  (`kisa-validate.yml`은 PR 쪽 코드를 실행하므로 같은 PR이 고칠 수 있다 — 그래서 범위 판정은 이쪽에서 한다.)
- 그래서 **렌더러·틀·검사기를 고치는 PR과 새 호 PR은 나눈다.** 렌더러를 고치고 HTML을 다시 만드는 PR(tools + docs)은 대상이 아니다.
- **필수 검사로 지정하지 않았다.** main에 필수 검사를 걸면 PR 없이 main에 직접 push하는 `daily.yml`·`portal.yml`이 거절된다.
  따라서 이 검사가 빨간색이면 병합하지 않는 것은 사람이 지키는 규칙이다.
- 이 workflow는 main에 병합된 뒤부터 동작한다(`pull_request_target`은 main 쪽 파일을 쓰므로, 이 파일을 추가하는 PR 자체에서는 돌지 않는다).
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

목록에 없는 주차의 데이터는 새 호다. 구조화 칸으로 쓰고 새 호 규칙(`check_new_issue()`)을 통과해야 한다.

## 새 호 — 구조화 칸 (관문 열림)

새 호의 항목 머리 줄(제목 아래 회색 줄)은 글자(`meta`·`meta_refs`)로 쓰지 않고 구조화 칸으로 적는다.
렌더러가 그 값으로 머리 줄을 만든다. 한 항목에 두 방식을 섞으면 실패한다. 글자 머리 줄은 이전된 호 전용이다.

- **`vulnerabilities[]`** — 기록한 취약점마다 네 칸. 값이 없으면 글자가 아니라 상태로 적는다.
  - `cve`: `value`(id 필수) / `unknown` / `not_assigned`(CVE 미부여)
  - `cvss`: `value`(점수 0.0~10.0 소수 한 자리·버전 3.0/3.1/4.0·평가 주체·출처) / `unknown`
  - `exploitation`: `confirmed` / `no_report`(기준일 `as_of` 필수) / `unknown`
  - `kev`: `listed`(등재일·기한·출처) / `not_listed` / `not_applicable` / `unknown`
- **`cve_total`** — 공지 전체 CVE 수(일부만 기록할 때). **`vendor_rating`** — 벤더 등급과 건수. **`addition`** — "긴급 추가".
- **`notices`** — `kisa`(`value`: 번호·게시일 / `none_in_period`: 확인한 대상 기간의 보호나라 게시판에 일치하는 공지가 없었음),
  `vendor`(공지 목록 / `unknown` / `not_applicable`).
- **출처** — `sources`에 `id`·`kind`·`viewed`를 붙이고 사실 칸은 `src`로 그 id를 가리킨다.
- **`checks`** — 호 단위 확인 기록. `kev`(조회한 판·주소·확인 시각·complete), `kisa`(확인 기간·마지막 번호·주소·확인 시각·complete).
  KEV의 `complete: true`는 "그 판본의 전체 KEV 목록을 확보했고, 구조화 데이터에 **기록된** 모든 CVE를 그 목록에서 조회했다"는 뜻이다.
  `cve_total`이 기록 수보다 큰 일부 기록형에서 기록하지 않은 CVE까지 조회했다는 뜻은 아니다.

주요 규칙(`validate.py`의 `check_new_issue()`):

- 근거로 쓸 수 있는 출처 종류: CVSS = 평가 주체에 맞는 출처(vendor→vendor, nvd→nvd, cisa-adp→cve),
  악용 확인 = kev·vendor·kisa, 보고 없음 = vendor·kisa, KEV = kev, KISA = kisa, 벤더 공지·등급 = vendor.
  research·news·other와 미열람(`viewed: false`) 출처는 근거로 쓸 수 없다.
- 출처 주소: kisa = www.boho.or.kr, kev = www.cisa.gov · github.com/cisagov/kev-data · raw.githubusercontent.com/cisagov/kev-data
  (출처의 kind=kev와 checks.kev.url 모두), nvd = nvd.nist.gov,
  cve = www.cve.org · cveawg.mitre.org. vendor는 이 네 종류의 주소가 아니어야 한다. 새 호는 모두 https.
- KEV·KISA는 "미확인"을 쓸 수 없다. CVE가 있으면 KEV는 등재/미등재, CVE 미부여면 해당 없음, CVE 미확인일 때만 미확인.
  미등재는 KEV 확인 기록이 complete일 때만, `none_in_period`는 KISA 확인 기록이 complete이고 대상 주간 전체를 덮을 때만.
- 악용 확인의 근거가 KEV 출처면 그 취약점의 KEV 상태는 listed여야 한다.
- 확인 기록의 `checked_at`은 실제로 있는 날짜·시각이어야 한다.
- schema를 통과한 데이터라면 `check_new_issue()`는 예외 없이 실패 메시지 목록을 돌려준다.
- KEV 등재면 악용 상태는 반드시 confirmed, 위험도는 긴급·높음만.
- 날짜: KEV 기한 ≥ 등재일, 등재일·KISA 게시일·벤더 공지일·as_of ≤ 발행일(KEV 기한은 발행일 뒤여도 됨),
  KEV 판 날짜 ≤ 발행일이고 모든 등재일 이상, 같은 CVE의 KEV 기록과 같은 KISA 번호의 게시일은 호 안에서 같아야 함.
- 제목의 CVE는 모두 목록에 있어야 하고 중복 금지, `cve_total` ≥ 기록한 수.
- 실패로 두지 않는 것: 벤더 공지일 ≤ KISA 게시일, KISA 번호와 게시일 순서, 신규 항목의 KISA 게시일 ≥ 대상 주간 시작.

머리 줄 문구(`render.py`의 `structured_headline()`): `위험도 · CVSS [· 벤더 등급] · 악용 | KISA · [벤더 공지 ·] KEV`.
"전체 수"는 `cve_total`이 있으면 그 값, 없으면 기록한 취약점 수다. 일부만 기록했으면 단정하지 않고 범위를 밝힌다.

- CVSS: 값이 없으면 "CVSS [미확인]"(벤더 등급이 있어도 대체하지 않고 나란히). "CVSS 최대"는 전체를 다 기록했고 모두 점수가 있을 때만.
- 악용: 전부 확인이면 "악용 확인", 일부면 "N건 악용 확인". 기록한 것이 모두 보고 없음이면 "보고 없음(M/D 기준)",
  일부만 기록했으면 "보고 없음(기록 N건 · M/D 기준)". 그 밖은 "악용 [미확인]".
- KISA: "KISA #번호(M/D 게시)". `none_in_period`이면 "보호나라 대상 기간 공지 없음"(대상 기간 게시판에 일치하는 공지가 없었다는 뜻).
- KEV: "KEV 등재 M/D(기한 M/D)" 또는 날짜가 다르면 "KEV 등재 N건(가장 이른 기한 M/D)". 등재가 없으면 전부 기록했을 때 "KEV 미등재",
  일부만 기록했으면 "KEV 미등재(기록 N건 기준)". CVE 미부여면 "KEV 해당 없음", CVE 미확인이면 "KEV [미확인]".
- 날짜는 M/D(발행 연도와 다르면 연도 포함).

**2. 우선순위 표 — 새 호** (`render.py`의 `structured_priority_row()`): 최상위 `priority[]`를 쓰지 않고
항목마다 한 줄을 items 순서대로 만든다(표와 항목 1:1). 사람이 쓰는 것은 항목의 `priority` 칸뿐이다.

- `priority.target`(대상, 필수), `details`(취약점 설명 줄, 1줄 이상), `deadline`(권고 기한, 필수),
  `deadline_note`(기한 아래 짧은 말, 선택). `deadline_note`에는 숫자·CVE·KEV·KISA·#를 쓸 수 없고,
  KEV 등재 항목에는 쓸 수 없다(그 자리에 KEV 기한이 자동으로 나온다).
- 나머지는 구조화 칸에서 머리 줄과 같은 함수로 만든다.
  - 대상: target + 회색 "KISA #번호 · KEV M/D"(등재일이 서로 다르면 "KEV N건"). 둘 다 없으면 회색 줄 없음.
  - 핵심 취약점: 기록한 첫 CVE(굵게) + 전체 수가 2 이상이면 " 외 N건". CVE 미부여면 "CVE 미부여", 미확인이면 "CVE [미확인]".
    그 아래 details.
  - 위험도·악용: 위험도 / 회색 CVSS 문구(벤더 등급 포함) / 굵게 기호 + 악용 문구(확인 ●, 보고 없음 ○, 미확인 ◌).
    악용 확인이고 KEV 등재가 있으면 " · KEV M/D"(또는 "KEV N건"). 등재 없이 확인이면 회색 줄에 근거 종류
    ("벤더 확인" / "KISA 확인" / "벤더·KISA 확인").
  - 기한: deadline + 회색 "KEV 기한 M/D"(가장 이른 기한, 발행일보다 앞이면 " 경과"). KEV 등재가 없으면 deadline_note.
- 이전된 호는 지금처럼 최상위 `priority[]`(글자)를 쓰고 반드시 있어야 한다. 이전된 호 항목에 `priority` 칸이 있으면 실패,
  새 호에 최상위 `priority[]`가 있으면 실패.

**관문이 열렸다.** `validate.py`는 면제 목록 밖 주차(새 호)마다 새 호 규칙을 실행한다.
형식·파일 이름·날짜·면제 목록 대조·렌더 일치·HTML 필수 요소·폴더 검사도 지금처럼 모두 적용된다.
이전된 호(면제 목록)에는 구조화 칸을 쓸 수 없다.

### 새 호를 올리는 순서

1. 최신 main에서 브랜치를 만든다.
2. 데이터를 쓴다: `content/kisa-cert/<week_start>.json` (구조화 칸, 출처, 확인 기록 `checks`).
3. `python tools/kisa/render.py <week_start>` — `docs/kisa-cert/kisa_weekly_<week_start>_public.html`이 만들어진다. HTML은 직접 고치지 않는다.
4. `python tools/kisa/validate.py` — 통과해야 한다.
5. `python -m unittest discover -s tools/kisa/tests -v` — 통과해야 한다.
6. PR을 올린다. **새 호 PR에는 `content/kisa-cert/<week_start>.json`과 `docs/kisa-cert/<파일>.html` 두 개만 넣는다.**
   다른 파일(검사기·렌더러·틀·workflow·목록 등)을 섞으면 kisa-pr-scope가 빨간색이 된다. 그런 변경은 별도 PR로 먼저 올린다.
   목록(manifest)은 병합 후 portal-manifest 워크플로가 갱신하므로 PR에 넣지 않는다.

### 검사기가 확인하지 못하는 것 — 사람이 본다

- 값이 실제 KEV·KISA·벤더 공지와 같은지(검사기는 네트워크를 쓰지 않는다. 형식·범위·호 안 일관성까지만 본다).
- 호와 호 사이의 일관성(예: 지난 호와 같은 CVE의 KEV 등재일·악용 상태).
- 사람이 쓰는 글 — 한눈에 보기, 본문(상황·조치·확인), 대상별 권고, 표의 설명 줄(`details`) — 이 구조화 칸과 맞는지.

시험 데이터는 `tools/kisa/tests/fixtures/`의 가상 호다:

```bash
python -m unittest discover -s tools/kisa/tests -v
```

## 과도기 절차 (첫 구조화 호가 성공할 때까지)

첫 구조화 호가 위 순서로 성공할 때까지는 이 절차도 계속 쓸 수 있다.
주간 리포트를 기존 방식대로 HTML로 만든다. 다만 **웹 업로드로 main에 바로 올리지 않는다.**

1. 최신 main에서 브랜치를 만든다.
2. HTML을 `docs/kisa-cert/kisa_weekly_<대상 주간 시작일>_public.html`로 넣는다.
   머리말의 `대상 기간: … | 발행: …` 줄을 지켜야 목록 날짜가 맞게 나온다.
3. 같은 변경에서 `validate.py`의 `LEGACY_HTML`에 그 파일 이름을 추가한다.
4. `python tools/kisa/validate.py`가 통과하는지, `python tools/build_manifest.py --check`에
   `주의:` 경고(발행일을 못 읽음, 같은 주차 중복 등)가 없는지 확인한 뒤 PR로 올린다.
   이때 `필요: 목록 갱신`은 정상이다 — 목록(manifest)은 병합 후 portal-manifest 워크플로가 갱신하므로
   PR에 넣지 않는다.
