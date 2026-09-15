# 오늘의 보안이슈

국내외 보안·개인정보보호 RSS를 매일 아침 자동 수집해 정적 페이지와 RSS로 발행합니다.
GitHub Actions에서 실행되고 GitHub Pages로 공개되므로 **서버·비용·외부 의존성이 없습니다**
(Python 표준 라이브러리만 사용).

공개 주소: **https://danny-secnews.github.io**

```
매일 08:40 KST  →  Actions 실행  →  docs/ 자동 커밋  →  Pages 즉시 반영
                                                        ↓
                                        고정 링크 1줄을 카카오톡에 게시
```

## 설치

1. **저장소 생성** — GitHub 계정 `danny-secnews`로 로그인한 뒤,
   저장소 이름을 정확히 **`danny-secnews.github.io`** 로 만듭니다. **Public**이어야 합니다.
   (이 이름이어야 주소에 `/저장소이름/` 경로가 붙지 않습니다.)

2. **파일 업로드**

   ```bash
   git init
   git add .
   git commit -m "init: 오늘의 보안이슈"
   git branch -M main
   git remote add origin https://github.com/danny-secnews/danny-secnews.github.io.git
   git push -u origin main
   ```

3. **Actions 쓰기 권한** — `Settings → Actions → General → Workflow permissions`
   → **Read and write permissions** → Save

4. **Pages 활성화** — `Settings → Pages`
   → Source: **Deploy from a branch** / Branch: **main** / 폴더: **/docs** → Save

5. **첫 발행** — `Actions → 오늘의 보안이슈 발행 → Run workflow`

`base_url`은 Actions에서 저장소 정보로 자동 보정되므로 손댈 필요가 없습니다.
나중에 커스텀 도메인을 붙이면 `feeds.json`의 `base_url`에 그 주소를 넣으면 되고,
그때는 자동 보정이 비활성화되어 입력한 값이 그대로 쓰입니다.

## 매일 하는 일

페이지 상단의 **"🔗 카카오톡 공유용 링크 복사"** 버튼을 누르면 제목과 그날 고정 링크가
함께 복사됩니다. 카카오톡 프로필 게시물에 붙여넣기만 하면 끝입니다.

> 카카오는 프로필 "내 소식" 게시를 위한 공개 API를 제공하지 않습니다.
> (카카오스토리 API 2023-11-15 종료, 카카오톡 채널 포스트도 API 미제공)
> 따라서 게시 자체의 완전 자동화는 불가능하며, 이 구조가 현실적인 최선입니다.

## 설정

`feeds.json` 하나만 고치면 됩니다. 응답하지 않는 피드는 자동으로 건너뜁니다.

| 항목 | 설명 |
|---|---|
| `categories[].feeds` | 수집원 목록. 카테고리째 추가·삭제 가능 |
| `lookback_hours` | 몇 시간 이내 기사만 수집할지 (기본 30시간 = 전일 기준) |
| `max_items_per_category` | 카테고리당 최대 노출 건수 |
| `highlight_keywords` | 포함 시 **주요** 배지가 붙고 상단으로 정렬되는 키워드 |

CVE 번호는 제목·요약에서 자동 추출해 배지로 표시합니다.

## 로컬 실행

```bash
python3 scripts/build.py              # 실제 수집 후 생성
python3 scripts/build.py --mock       # 샘플 데이터로 디자인 확인
python3 scripts/build.py --allow-empty  # 수집 0건이어도 페이지 생성
```

## 구조

```
feeds.json                  수집원·정책 설정
scripts/collect.py          RSS/Atom 수집·파싱·중복제거 (표준 라이브러리)
scripts/build.py            HTML·RSS 렌더링
.github/workflows/daily.yml 매일 08:40 KST 실행
docs/                       GitHub Pages 공개 디렉터리 (자동 생성)
  ├ index.html              최신호 + 지난 발행 목록
  ├ posts/YYYY-MM-DD.html   일자별 고정 링크
  ├ rss.xml                 구독용 피드
  └ data/                   원본 JSON 보관 (재가공·통계용)
```

일자별 JSON이 `docs/data/`에 쌓이므로, 나중에 주간 리포트나 메일 뉴스레터로
재가공할 때 다시 수집할 필요가 없습니다.
