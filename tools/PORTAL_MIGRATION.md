# 포털 개편 적용 순서 (최종)

압축을 저장소 루트에 풀면 경로가 그대로 맞습니다. 생성 코드(scripts/build.py)와
데일리 워크플로 수정본이 함께 들어 있습니다.

## 바뀐 뒤 구조

```
docs/
├── index.html            포털 (고정 파일 — build.py가 더 이상 쓰지 않음)
├── rss.xml               위치 유지 (구독 주소 그대로)
├── assets/style.css      기존 데일리 스타일 (그대로)
├── assets/portal.css     포털·목록 페이지 공용
├── assets/portal.js
├── assets/site-nav.js    본문 페이지 공통 상단 바
├── data/archive.json     기존 (지난 발행 목록 — build.py)
├── data/manifest.json    포털 목록 (tools/build_manifest.py — 손으로 고치지 않음)
├── daily/                index.html(최신호 + 지난 발행) + YYYY-MM-DD.html  ← build.py 출력
├── kisa-cert/            kisa_weekly_*.html + index.html(목록)
├── law/                  YYYY-MM-DD-주제.html + index.html(목록)
└── posts/                옛 주소 안내 페이지만 남음 — 유입이 끊기면 삭제
```

배포는 지금처럼 main 브랜치 /docs 그대로입니다(워크플로에 배포 단계가 없고 docs/.nojekyll 사용).

## 압축에 든 파일

| 파일 | 구분 |
|---|---|
| docs/index.html, docs/assets/portal.css·portal.js·site-nav.js | 새 파일 (index.html은 교체) |
| docs/kisa-cert/index.html, docs/law/index.html | 새 파일 |
| tools/migrate_to_portal.py, tools/build_manifest.py, tools/PORTAL_MIGRATION.md | 새 파일 |
| .github/workflows/portal.yml | 새 파일 |
| scripts/build.py | **교체** — docs/daily 출력, RSS link /daily/ + guid 유지 |
| .github/workflows/daily.yml | **교체** — 포털 단계(continue-on-error), 푸시 재시도, 마지막 점검 |

**주의 — daily.yml 파일 이름**: 저장소의 데일리 워크플로 파일 이름이 `daily.yml`이 아니면,
압축의 daily.yml 내용을 **기존 파일에 덮어쓰고** daily.yml은 지우세요.
둘 다 남으면 08:40에 데일리가 두 번 돕니다.

## 실행 순서 — 한 커밋으로 푸시

1. Actions → '오늘의 보안이슈 발행' → **Disable** (작업 중 08:40 실행 방지)
2. 로컬 저장소 최신화: `git pull`
3. 압축을 저장소 루트에 풀기 (위 daily.yml 주의 확인)
4. `python tools/migrate_to_portal.py` — 계획 확인
   - 보류(security-news-* 2개): 구분을 정해 `RULES`에 한 줄 추가하거나, 지우거나, 그대로 두기
   - 같은 주차 KISA(9/7 ×3, 9/14 ×2): 최종본만 남기거나 나머지에 `<meta name="portal" content="hide">`
5. `python tools/migrate_to_portal.py --apply`
6. `python tools/build_manifest.py`
7. 로컬 확인: `python -m http.server -d docs 8000`
   - http://localhost:8000/ 포털 · /daily/ (최신호로 넘어감) · /kisa-cert/ · /law/
   - http://localhost:8000/posts/2026-09-30.html → /daily/2026-09-30.html 로 넘어가는지
8. 커밋·푸시 (한 커밋):
   `git add docs tools scripts/build.py .github && git commit -m "포털 개편" && git push`
9. 데일리 워크플로 **Enable** → Run workflow 1회 (또는 다음 날 08:40 정기 실행으로 확인)
   - 수동 실행은 오늘 호를 최신 수집으로 다시 만듭니다(내용이 아침 판과 조금 다를 수 있음)
   - 그 전까지 /daily/는 최신호로 넘겨 주는 임시 페이지라 방문자에게 문제 없음
10. 확인: 사이트 루트=포털, /daily/=오늘 호, 옛 /posts/ 주소 이동, rss.xml의 link=/daily/·guid=예전 값

**되돌리기**: `git revert <포털 개편 커밋>` 한 번이면 원래 구조로 돌아갑니다.

## 데일리 워크플로가 하는 일 (수정본)

1. 수집 및 페이지 생성 — `python scripts/build.py` (docs/daily/에 출력)
2. 포털 목록 갱신 — `python tools/build_manifest.py`, **continue-on-error**
3. 포털 페이지 확인 — `docs/index.html`에 `data-page="portal"`이 있는지 확인.
   없으면 즉시 실패하며 커밋·푸시하지 않음. 구형 build.py가 포털을 덮어쓰는 사고를 main 반영 전에 차단
4. 변경사항 커밋 — `git add docs`. 푸시가 거절되면(그사이 포털 목록 커밋이 먼저 올라감)
   `git pull --rebase --autostash` 후 다시 푸시. 목록 파일이 충돌하면 다시 생성해서 해결
5. 포털 점검 결과 — 2번이 실패했지만 3번 포털 확인은 정상인 경우,
   **데일리가 발행된 뒤** 빨간불 + 실패 메일

구형 `scripts/build.py`가 남아 `docs/index.html`을 덮어쓰는 경우에는 포털 보호를 위해
해당 실행의 데일리 발행도 중단됩니다. `scripts/build.py`를 현재 버전으로 교체한 뒤
GitHub Actions에서 `Run workflow`를 다시 실행하면 됩니다.

## 공통 상단 바

데일리·KISA·법령 본문 맨 위에 `보안정보 브리핑 | 데일리 · KISA 주간 · 법령·제도 분석` 바.

- 본문 CSS는 그대로 — 바는 Shadow DOM 안에서 따로 그림
- 데일리는 build.py 템플릿에 한 줄 포함, KISA·법령은 업로드하면 portal.yml이 자동으로 한 줄 추가
- 인쇄·PDF 저장 때 숨김. 파일로 따로 열면(첨부 등) 바 없이 원래대로 보임
- 빼고 싶은 페이지: `<head>`에 `<meta name="portal-nav" content="off">`

## 이후 운영

- **KISA 주간·법령·제도 분석 자료**: 해당 폴더에 HTML만 올리면 portal.yml이 목록 갱신 + 상단 바 추가
  - KISA 주간을 Cowork 등 저장소 밖에서 만든다면 그쪽 저장 위치를 `docs/kisa-cert/`로
- **파일 이름**: KISA `kisa_weekly_YYYY-MM-DD_….html`(대상 주간 시작일),
  법령 `YYYY-MM-DD-주제.html`(**게시일**). 또는 `<meta name="portal-date" content="YYYY-MM-DD">`
- **KISA 목록 날짜**: 본문 머리말 `대상 기간: … | 발행: YYYY.MM.DD`의 **발행일** (portal-date 메타가 있으면 그게 우선)
  - 그 줄을 못 읽거나 발행일이 대상 기간 시작일~31일 뒤 범위 밖이면 경고 후 파일 이름 날짜를 씀
  - 파일 이름은 지금처럼 대상 주간 시작일로 짓는다 (같은 주차 중복 확인도 이 기준)
- **목록에서 빼기**: `<meta name="portal" content="hide">` (주소로는 계속 열림)
- **제목·요약**: 각 파일의 `<title>`, `<meta name="description">`
- **사이트 이름 변경**: docs/index.html, kisa-cert/index.html, law/index.html, site-nav.js의 `SITE_NAME`
- **저장소 이전 시**: build.py의 RSS guid 줄을 `base` 대신 옛 주소 문자열로 고정 (구독자 중복 방지)
- **posts/ 안내 페이지**: 옛 링크 유입이 끊기면(몇 달 뒤) 폴더째 삭제
