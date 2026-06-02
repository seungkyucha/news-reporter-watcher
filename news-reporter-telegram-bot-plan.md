# 기자 기사 텔레그램 알림봇 개발 계획서

> **한 줄 소개**: GitHub Actions와 네이버 검색 API를 활용해, 지정한 기자의 새 기사를 5분 간격으로 자동 감시하고 텔레그램으로 즉시 알림을 보내는 무서버(serverless) 알림봇.
>
> **핵심 가치**: 비개발자도 README만 보고 30분 안에 설치할 수 있어야 한다.

---

## 1. 프로젝트 개요

### 1.1 문제 정의

특정 기자의 신규 기사를 가능한 빨리 받아보고 싶은 사용자(홍보팀, 마케터, 정보분석가, 일반 독자)는 현재 다음과 같은 불편을 겪는다.

- 네이버 뉴스에서 기자 이름을 매번 수동 검색해야 한다.
- 알림 서비스가 있어도 기자 단위 필터링이 어렵다.
- RSS 기반 솔루션은 일부 언론사에만 제공되어 누락이 잦다.
- 직접 만들려면 서버, DB, 배포 환경이 필요해 진입장벽이 높다.

### 1.2 솔루션 컨셉

GitHub Actions의 주기 실행(cron) 기능을 백엔드로 사용하면 **서버 비용 0원**, **배포 작업 0회**로 자동화 시스템을 구축할 수 있다. 본 프로젝트는 다음의 4가지 외부 서비스만 조합한다.

1. **GitHub Actions** — 5분마다 스크립트를 자동 실행하는 무료 cron 인프라
2. **네이버 검색 API (뉴스)** — 국내 뉴스 검색 결과를 JSON으로 제공
3. **Telegram Bot API** — 개인/채널로 알림 메시지 전송
4. **GitHub Repository (JSON 파일)** — 이미 보낸 기사 이력을 저장하는 무료 DB 대용

### 1.3 차별점

- **무서버(Zero infra)**: AWS, GCP, Heroku 등 외부 서버 불필요
- **무비용(Zero cost)**: 모든 구성요소가 무료 티어 안에서 동작
- **무코딩(Zero coding)**: 비개발자도 `Use this template` → Secrets 입력 → 끝
- **개방형 설정(Open config)**: 기자 목록은 JSON 한 줄로 관리, 추가/삭제 자유

---

## 2. 최종 동작 시나리오

```text
[GitHub Actions cron: 5분 간격]
        │
        ▼
[Checkout repository]  ──► sent_articles.json 로드 (과거 전송 이력)
        │
        ▼
[REPORTERS Secret 로드]  ──► 감시할 기자 목록 (JSON 배열)
        │
        ▼
[기자별 루프 시작]
   │
   ├─► 네이버 뉴스 검색 API 호출 (sort=date, display=20)
   │
   ├─► 포함/제외 키워드 필터 적용
   │
   ├─► URL 정규화 → SHA-256 해시 → sent_articles.json 과 대조
   │
   ├─► 새 기사만 추출
   │
   └─► 텔레그램으로 한 건씩 전송 (Markdown 형식)
        │
        ▼
[sent_articles.json 업데이트]
        │
        ▼
[변경분 자동 commit & push]  ──► 다음 실행에서 다시 사용됨
        │
        ▼
[종료 — 다음 5분 후 재실행]
```

---

## 3. 요구사항 정의

### 3.1 기능 요구사항 (Functional)

| ID | 요구사항 | 우선순위 |
|---|---|:---:|
| FR-01 | 여러 기자를 동시 감시할 수 있어야 한다 | 必 |
| FR-02 | 기자별로 언론사명을 선택적으로 지정할 수 있어야 한다 | 必 |
| FR-03 | 기자별 포함 키워드(AND 조건)를 설정할 수 있어야 한다 | 必 |
| FR-04 | 기자별 제외 키워드(NOT 조건)를 설정할 수 있어야 한다 | 必 |
| FR-05 | 5분 간격으로 새 기사를 자동 감시해야 한다 | 必 |
| FR-06 | 이미 전송한 기사는 다시 보내지 않아야 한다 | 必 |
| FR-07 | 새 기사는 텔레그램으로 즉시 전송되어야 한다 | 必 |
| FR-08 | GitHub Actions UI에서 수동 실행이 가능해야 한다 | 必 |
| FR-09 | 별도 서버 없이 GitHub만으로 동작해야 한다 | 必 |
| FR-10 | 메시지에 언론사 / 기자명 / 제목 / 발행시각 / 링크 / 요약 포함 | 권장 |
| FR-11 | 전송 이력은 최근 5,000건만 유지 | 권장 |
| FR-12 | 한 기자 처리 중 실패해도 전체 실행은 계속됨 | 권장 |

### 3.2 비기능 요구사항 (Non-functional)

- **사용성**: README만 보고 비개발자가 설치 가능해야 한다.
- **보안**: API 키 / 토큰은 절대 코드에 저장하지 않고 GitHub Secrets만 사용한다.
- **안정성**: 동시 실행 충돌 방지를 위해 `concurrency` 설정을 적용한다.
- **효율성**: 네이버 API 호출 수가 무료 한도(25,000건/일)를 넘지 않도록 한다.
- **유지성**: `sent_articles.json` 커밋 충돌 가능성을 최소화한다(rebase 적용).
- **확장성**: 향후 Slack, Discord 추가 알림 채널을 쉽게 붙일 수 있도록 모듈화한다.

---

## 4. 기술 스택

| 분류 | 선택 기술 | 선택 이유 |
|---|---|---|
| 실행 환경 | GitHub Actions | 별도 서버 불필요, cron 무료 지원, 비개발자에게도 친숙 |
| 언어 | Python 3.11 | HTTP/JSON 처리 단순, 외부 의존성 최소화 가능 |
| 뉴스 검색 | 네이버 검색 API (news) | 국내 뉴스 커버리지 최강, JSON 응답, 무료 25,000 req/day |
| 알림 | Telegram Bot API | 개인 / 채널 모두 지원, 토큰만으로 사용 가능 |
| 중복 저장 | 저장소 내 JSON 파일 | 외부 DB 불필요, GitHub 자체가 무료 저장소 |
| 패키지 관리 | requirements.txt | GitHub Actions에서 한 줄로 설치 가능 |
| 배포 방식 | GitHub Template Repository | "Use this template" 클릭 한 번으로 복제 가능 |

---

## 5. 저장소 구조

```text
news-reporter-telegram-bot/
├── .github/
│   └── workflows/
│       └── watch-news.yml          # 5분 cron 워크플로우
├── data/
│   └── sent_articles.json          # 전송 이력 (자동 갱신)
├── watcher.py                      # 메인 스크립트
├── requirements.txt                # Python 의존성
├── README.md                       # 비개발자용 설치 가이드
└── .gitignore
```

---

## 6. GitHub Secrets 설계

사용자는 저장소의 **Settings → Secrets and variables → Actions** 에서 아래 값을 한 번씩만 입력하면 된다.

| Secret 이름 | 필수 | 설명 | 예시 |
|---|:---:|---|---|
| `NAVER_CLIENT_ID` | 必 | 네이버 개발자 센터에서 발급한 Client ID | `abc123xyz` |
| `NAVER_CLIENT_SECRET` | 必 | 네이버 개발자 센터에서 발급한 Client Secret | `SECRET_value` |
| `TELEGRAM_BOT_TOKEN` | 必 | BotFather로 발급한 봇 토큰 | `7123456789:AAH...` |
| `TELEGRAM_CHAT_ID` | 必 | 알림을 받을 채팅방 또는 채널 ID | `-1001234567890` |
| `REPORTERS` | 必 | 감시할 기자 목록 (JSON 배열, 한 줄) | 7장 참고 |

> ⚠️ 모든 값은 GitHub Secrets에 저장되어 워크플로우 로그에도 마스킹된다.

---

## 7. REPORTERS 설정 형식

`REPORTERS` Secret 은 **JSON 배열 한 줄**로 저장한다.

### 7.1 가독성 좋은 표기(설명용)

```json
[
  {
    "name": "홍길동",
    "press": "한국경제",
    "include_keywords": ["AI", "반도체"],
    "exclude_keywords": ["부고", "인사"]
  },
  {
    "name": "김철수",
    "press": "매일경제",
    "include_keywords": ["스타트업", "투자"],
    "exclude_keywords": []
  },
  {
    "name": "이영희",
    "press": "",
    "include_keywords": [],
    "exclude_keywords": ["부고", "인사"]
  }
]
```

### 7.2 GitHub Secrets 입력용 (한 줄)

```json
[{"name":"홍길동","press":"한국경제","include_keywords":["AI","반도체"],"exclude_keywords":["부고","인사"]},{"name":"김철수","press":"매일경제","include_keywords":["스타트업","투자"],"exclude_keywords":[]}]
```

### 7.3 필드 설명

| 필드 | 타입 | 필수 | 설명 |
|---|---|:---:|---|
| `name` | string | 必 | 기자 이름 (검색어에 자동으로 "기자" 키워드가 붙음) |
| `press` | string | 任 | 언론사명 (빈 문자열이면 언론사 제한 없음) |
| `include_keywords` | string[] | 任 | 모든 키워드가 제목/요약에 포함되어야 함 (AND) |
| `exclude_keywords` | string[] | 任 | 하나라도 제목/요약에 있으면 제외 (NOT) |

---

## 8. 중복 방지 설계

### 8.1 저장 파일

**경로**: `data/sent_articles.json`

**초기 상태**:

```json
{ "sent": [] }
```

**전송 후 예시**:

```json
{
  "sent": [
    {
      "id": "sha256-hash-of-url",
      "reporter": "홍길동",
      "press": "한국경제",
      "title": "삼성전자, AI 반도체 신제품 공개",
      "url": "https://news.example.com/article/1",
      "published_at": "Wed, 27 May 2026 09:15:00 +0900",
      "sent_at": "2026-05-27T09:20:03+09:00"
    }
  ]
}
```

### 8.2 중복 판단 알고리즘

```text
1. 원본 URL  →  normalize_url(url)
       └─ query string 제거
       └─ fragment(#) 제거
       └─ 앞뒤 공백 제거
2. 정규화된 URL  →  sha256()  →  article_id
3. article_id 가 sent_articles.json[*].id 에 존재하면 스킵
```

MVP에서는 **URL 전역 중복 기준**을 사용한다. 같은 기사가 여러 기자 조건에 동시에 매칭되어도 텔레그램에는 단 1회만 전송된다.

향후 공동기명 기사를 기자별로 따로 받고 싶을 경우, ID 생성식을 `SHA-256(reporter_name + normalized_url)` 로 변경할 수 있다.

### 8.3 저장 용량 관리

- `sent` 배열은 **최근 5,000건**까지만 유지한다.
- 5,000건 초과 시 가장 오래된 항목부터 제거한다.
- 5,000건 기준은 기자 30명 × 5분 간격 환경에서 약 1주 분량에 해당한다.

---

## 9. GitHub Actions 워크플로우 설계

**파일 경로**: `.github/workflows/watch-news.yml`

```yaml
name: Watch reporter news

on:
  schedule:
    - cron: "2-59/5 * * * *"     # 매시 2,7,12,...,57분 (정각 부하 회피)
  workflow_dispatch:              # UI 수동 실행 허용

permissions:
  contents: write                 # JSON 이력 파일 커밋용

concurrency:
  group: news-reporter-watcher    # 동시 실행 방지
  cancel-in-progress: false

jobs:
  watch:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run watcher
        env:
          NAVER_CLIENT_ID:     ${{ secrets.NAVER_CLIENT_ID }}
          NAVER_CLIENT_SECRET: ${{ secrets.NAVER_CLIENT_SECRET }}
          TELEGRAM_BOT_TOKEN:  ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID:    ${{ secrets.TELEGRAM_CHAT_ID }}
          REPORTERS:           ${{ secrets.REPORTERS }}
        run: python watcher.py

      - name: Commit sent article history
        run: |
          git config user.name  "news-watcher-bot"
          git config user.email "actions@github.com"
          git add data/sent_articles.json
          git diff --cached --quiet || git commit -m "Update sent article history"
          git pull --rebase
          git push
```

### 9.1 설계 근거

- `cron: "2-59/5 * * * *"` — 정각이 아닌 매시 2분부터 5분 간격으로 실행해 GitHub 인프라 정각 혼잡을 피한다.
- `workflow_dispatch` — UI에서 즉시 테스트 실행 가능.
- `permissions: contents: write` — `sent_articles.json` 커밋에 필요.
- `concurrency` — 이전 실행이 끝나기 전에 새 실행이 시작되어 커밋이 충돌하는 것을 방지.
- `git pull --rebase` — 직접 푸시 직전 원격 변경분을 흡수해 push 실패를 줄인다.

---

## 10. Python 프로그램 설계

### 10.1 주요 함수

| 함수 | 책임 |
|---|---|
| `load_reporters()` | `REPORTERS` JSON 파싱 및 검증 |
| `build_query(reporter)` | 네이버 검색용 쿼리 문자열 조립 |
| `search_naver_news(query)` | 네이버 검색 API 호출 (sort=date) |
| `passes_filters(item, reporter)` | 포함 / 제외 키워드 필터링 |
| `load_sent()` | 기존 전송 이력 파일 로드 |
| `save_sent(items)` | 전송 이력 갱신 + 5,000건 트리밍 |
| `article_id(url)` | URL 정규화 → SHA-256 |
| `format_message(item, reporter)` | 텔레그램 메시지 본문 작성 |
| `send_telegram(message)` | Telegram Bot API 호출 |
| `main()` | 전체 흐름 제어 |

### 10.2 검색 쿼리 규칙

**템플릿**:
```text
"{기자명} 기자" {언론사명} {포함키워드들 공백 구분}
```

**예시**:
```text
"홍길동 기자" 한국경제 AI 반도체
```

**API 옵션**:
- `display=20` (한 번 호출당 결과 수)
- `start=1`
- `sort=date` (최신순)

### 10.3 필터링 정책

- `include_keywords` 가 비어있지 않으면 **모든** 키워드가 제목 또는 요약에 포함되어야 한다 (AND).
- `exclude_keywords` 중 **하나라도** 제목 또는 요약에 있으면 즉시 제외한다 (NOT).
- 기자명은 검색 쿼리에 이미 포함되므로 결과에서 강하게 재검증하지 않는다.
- 언론사명은 네이버 응답에 항상 표시되지 않을 수 있어 쿼리에만 사용하고 결과 필터에서는 강제하지 않는다 (MVP 정책).

### 10.4 텔레그램 메시지 형식

```text
[새 기사] 홍길동 기자

언론사: 한국경제
제목: 삼성전자, AI 반도체 신제품 공개
시간: 2026-05-27 09:15
링크: https://news.example.com/article/1

요약: 삼성전자가 차세대 AI 가속기를 공개하며 ...
```

- HTML 태그(`<b>`, `</b>` 등)는 사전에 모두 제거한다.
- 메시지는 plain text 또는 Markdown 모드로 전송한다.
- `disable_web_page_preview=false` 로 두면 텔레그램이 자동 미리보기를 만들어준다.

---

## 11. requirements.txt

```text
requests==2.32.3
python-dateutil==2.9.0.post0
```

> 최소 의존성 원칙 — 두 패키지면 모든 기능이 구현 가능하다.

---

## 12. README (비개발자용 단계별 설치 가이드)

> 본 절은 README.md 의 목차와 실제 안내 문구의 초안이다. 비개발자가 첫 화면에서 마지막 화면까지 헤매지 않도록, **클릭 단위**로 안내한다.

### 12.1 이 봇이 하는 일 (30초 소개)

- 지정한 기자의 새 기사를 **5분마다** 자동 검사
- 새 기사가 발견되면 **텔레그램으로 즉시 전송**
- 한 번 보낸 기사는 다시 보내지 않음
- 별도 서버 / 호스팅 비용 없이 **GitHub 무료 계정**만으로 동작

### 12.2 미리 준비할 것

| 준비물 | 비용 | 소요 시간 |
|---|---|---|
| GitHub 계정 | 무료 | 1분 |
| 네이버 개발자 센터 애플리케이션 | 무료 | 3분 |
| 텔레그램 계정 | 무료 | (이미 있다면 0분) |
| 알림을 받을 채팅방 또는 채널 | 무료 | 1분 |

### 12.3 전체 설치 흐름 (9단계)

```text
1. 템플릿 저장소 복사 (Use this template)
2. 새 저장소를 Private 으로 생성
3. 네이버 개발자 센터에서 API 키 발급
4. Telegram BotFather 에서 봇 생성
5. 텔레그램 채팅방 / 채널에 봇 초대
6. chat_id 확인
7. GitHub Secrets 5개 입력
8. Actions 탭에서 워크플로우 활성화
9. Run workflow 로 테스트 → 텔레그램 확인
```

### 12.4 단계별 상세 가이드

#### Step 1. 템플릿 저장소 복사하기

1. 본 저장소 페이지 상단의 초록색 **`Use this template`** 버튼을 누른다.
2. **`Create a new repository`** 를 선택한다.
3. Repository name 을 자유롭게 정한다. (예: `my-news-watcher`)
4. **Private** 으로 두는 것을 권장한다. (Secrets 보호 차원)
5. **`Create repository`** 클릭.

#### Step 2. 네이버 검색 API 키 발급

1. [네이버 개발자 센터](https://developers.naver.com) 접속 후 로그인.
2. 상단 **`Application`** → **`애플리케이션 등록`** 클릭.
3. 애플리케이션 이름 입력 (예: `news-watcher`).
4. **사용 API**에서 **`검색`** 체크.
5. **비로그인 오픈 API 서비스 환경**에서 **`WEB 설정`** 선택, URL은 `https://github.com` 입력.
6. 등록 완료 후 표시되는 **Client ID** 와 **Client Secret** 을 메모장에 복사해 둔다.

#### Step 3. Telegram 봇 생성

1. 텔레그램에서 **@BotFather** 와 대화 시작.
2. 명령어 `/newbot` 전송.
3. 봇 이름 (자유) 입력.
4. 봇 username (예: `my_news_watcher_bot`) 입력.
5. BotFather 가 알려주는 **HTTP API Token** 을 복사해 둔다.

   > 형식 예: `7123456789:AAH...` — 콜론(`:`)이 반드시 포함된다.

#### Step 4. 봇을 채팅방 / 채널에 초대

**개인 채팅으로 받기**:
1. 위에서 만든 봇과 1:1 채팅을 시작한다.
2. 봇에게 아무 메시지나 한 번 보낸다 (`/start` 등).

**그룹 / 채널로 받기**:
1. 그룹 또는 채널을 생성한다.
2. 멤버 / 관리자로 봇을 초대한다.
3. 채널이면 봇을 **관리자(Admin)** 로 지정해야 메시지 전송이 가능하다.

#### Step 5. chat_id 확인

가장 쉬운 방법: **@userinfobot** 또는 **@RawDataBot** 사용.

- **개인 채팅 chat_id**: 본인 텔레그램에서 @userinfobot 에게 `/start` → 표시되는 `Id` 값.
- **그룹 chat_id**: 봇이 들어있는 그룹에 @RawDataBot 을 초대 → `/start` → 표시되는 `chat.id` 값 (보통 마이너스 부호 포함, 예: `-1001234567890`).

> 채널 chat_id 는 일반적으로 `-100`으로 시작한다.

#### Step 6. GitHub Secrets 입력

1. Step 1 에서 만든 저장소 페이지로 이동.
2. **Settings → Secrets and variables → Actions** 메뉴 진입.
3. **`New repository secret`** 버튼으로 아래 5개를 차례로 등록한다.

| Name | Value (예시) |
|---|---|
| `NAVER_CLIENT_ID` | Step 2 에서 받은 Client ID |
| `NAVER_CLIENT_SECRET` | Step 2 에서 받은 Client Secret |
| `TELEGRAM_BOT_TOKEN` | Step 3 에서 받은 Bot Token |
| `TELEGRAM_CHAT_ID` | Step 5 에서 확인한 chat_id |
| `REPORTERS` | 7.2절의 **한 줄 JSON** 형식 |

#### Step 7. Actions 활성화

1. 저장소 상단의 **`Actions`** 탭 클릭.
2. 처음이라면 **`I understand my workflows, go ahead and enable them`** 버튼을 눌러 활성화.

#### Step 8. 첫 실행 테스트

1. Actions 탭 좌측에서 **`Watch reporter news`** 워크플로우 선택.
2. 오른쪽의 **`Run workflow`** → **`Run workflow`** 클릭.
3. 1~2분 후 로그를 확인한다 (초록 체크가 뜨면 성공).
4. 텔레그램에 알림이 오면 설치 완료!

#### Step 9. 자동 실행 확인

이후에는 GitHub Actions 가 5분마다 자동으로 실행된다. 별도 조작은 필요 없다.

### 12.5 자주 묻는 질문 (FAQ)

| 증상 | 가능한 원인 | 해결 |
|---|---|---|
| Actions 가 자동 실행되지 않음 | 워크플로우 비활성화 / 60일간 push가 없으면 cron 정지 | Actions 탭에서 활성화, 또는 Run workflow 한 번 실행 |
| 텔레그램에 메시지가 오지 않음 | Bot Token 또는 chat_id 오류, 봇이 채널 관리자가 아님 | Secrets 재확인, 봇 권한 확인 |
| 네이버 검색 결과가 비어 있음 | Client ID/Secret 오타, 호출 한도 초과 | 네이버 개발자 센터에서 키 재확인 |
| 같은 기사가 반복해서 옴 | `sent_articles.json` 커밋 실패 | Actions 로그에서 push 단계 오류 확인 |
| 새 기사가 전혀 안 옴 | include_keywords 가 너무 좁음 | 키워드 제거 또는 완화 |
| `Bad credentials` 로그 | 토큰 누락 | Secrets 5개가 모두 등록됐는지 확인 |

---

## 13. 개발 단계 (Phased Roadmap)

각 단계는 **완료 기준(DoD)** 을 갖춘다.

### Phase 1. 골격 구축
- 저장소 구조 생성
- `requirements.txt`, 초기 `sent_articles.json` 작성
- 워크플로우 YAML 작성
- **DoD**: workflow_dispatch 로 수동 실행 시 Python 스크립트가 호출됨

### Phase 2. 설정 로딩
- 환경변수 5종 로드
- `REPORTERS` JSON 파싱 + 스키마 검증
- 잘못된 JSON 입력 시 어느 필드가 문제인지 로그 출력
- **DoD**: 여러 기자 설정이 정상 파싱되며, 오설정 시 명확한 에러 표시

### Phase 3. 네이버 뉴스 검색
- 검색 쿼리 빌더
- 네이버 API 호출 + JSON 파싱
- HTML 태그 제거
- **DoD**: 기자별 검색 결과를 정상 수신, 한 기자 실패 시 다음 기자로 계속

### Phase 4. 필터링 & 중복 제거
- include / exclude 키워드 필터
- URL 정규화 + SHA-256 해시
- `sent_articles.json` 로드 / 저장
- **DoD**: 이미 보낸 기사는 절대 재전송되지 않음

### Phase 5. 텔레그램 전송
- `sendMessage` 호출
- 메시지 포맷터
- 전송 실패 격리 (다음 기사 처리 계속)
- **DoD**: 테스트 채팅방으로 정상 메시지 도착, 일부 실패가 전체를 멈추지 않음

### Phase 6. 자동 커밋
- 변경 감지 후에만 commit
- `git pull --rebase` 후 push
- **DoD**: 새 기사 전송 후 이력 파일이 저장소에 반영되며, 빈 commit은 없음

### Phase 7. 비개발자용 문서화
- 12장 README 완성
- 스크린샷 / 그림 자리 placeholder 삽입
- **DoD**: 비개발자가 README 만 보고 처음부터 끝까지 설치 가능

---

## 14. 테스트 계획

### 14.1 로컬 테스트

```bash
export NAVER_CLIENT_ID="..."
export NAVER_CLIENT_SECRET="..."
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
export REPORTERS='[{"name":"홍길동","press":"한국경제","include_keywords":[],"exclude_keywords":[]}]'
python watcher.py
```

**확인 포인트**:
- 환경변수 누락 시 명확한 오류
- REPORTERS JSON 파싱 결과
- 네이버 API 응답 정상 여부
- 텔레그램 메시지 수신 여부
- `sent_articles.json` 갱신 여부
- 재실행 시 중복 전송이 막히는지

### 14.2 GitHub Actions 테스트

1. Secrets 5개 입력
2. **Run workflow** 수동 실행
3. 로그 확인 (각 단계 초록 체크)
4. 텔레그램 메시지 도착 확인
5. 커밋 히스토리에 `Update sent article history` 가 있는지 확인

### 14.3 시나리오별 예외 테스트

| 테스트 시나리오 | 기대 동작 |
|---|---|
| 잘못된 네이버 Client ID | "401 Unauthorized" 로그 후 다음 기자로 계속 |
| 잘못된 텔레그램 토큰 | "Telegram send failed" 로그 후 계속 |
| 잘못된 REPORTERS JSON | 어느 필드가 문제인지 명시한 에러 후 종료 |
| 너무 좁은 include_keywords | "0 new articles" 로그, 정상 종료 |
| 동일 기사 재검색 | 중복 ID 매칭으로 스킵, 텔레그램 전송 0건 |
| 기자 50명 설정 | 모든 기자에 대해 순차 검색 수행 |

---

## 15. 운영 정책

### 15.1 네이버 API 호출 수 시뮬레이션

5분 cron 기준 하루 실행 횟수: `24 × 12 = 288회`

| 기자 수 | 일일 호출 수 | 무료 한도(25,000/일) 대비 |
|---:|---:|---|
| 1명 | 288 | 1.2% |
| 5명 | 1,440 | 5.8% |
| 10명 | 2,880 | 11.5% |
| 30명 | 8,640 | 34.6% |
| 50명 | 14,400 | 57.6% |
| 80명 | 23,040 | 92.2% |
| 100명 | 28,800 | **초과 (대용량 한도 신청 필요)** |

> **MVP 권장 한도: 30~50명**

### 15.2 이력 파일 관리

- `sent_articles.json` 은 최근 **5,000건**으로 자동 트리밍.
- 파일이 1MB 이상 커지면 Actions checkout / commit 속도가 체감적으로 느려진다.
- 장기적으로는 Supabase / Google Sheets / SQLite artifact 등 외부 저장소 전환을 고려.

### 15.3 GitHub Actions 운영 주의사항

- cron 은 **UTC** 기준. 5분 간격은 한국 시간대도 그대로 적용.
- "5분 간격"은 **정확한 5분 0초 보장이 아님** — 인프라 혼잡 시 수 분 지연 가능.
- 60일간 저장소 push 가 없으면 cron 이 자동 비활성화될 수 있다 (GitHub 정책).
- Actions 한 잡은 **장기 실행에 부적합**. 본 봇은 5분 안에 종료되도록 설계.
- Public 저장소: cron 무료 / 무제한. Private 저장소: 월 2,000분 무료 분량 안에서 사용.

---

## 16. 향후 개선 과제

### 16.1 설정 편의성
- REPORTERS JSON 생성기 웹페이지 제공 (GitHub Pages)
- Google Form 기반 가이드형 설정 입력기
- 단계별 스크린샷 / 짧은 GIF 가이드 추가

### 16.2 검색 정확도
- 언론사별 RSS 보조 채널 추가
- 기자 페이지 직접 크롤러 플러그인
- 네이버 + RSS 결과 머지
- 제목 유사도 기반 중복 제거 (Levenshtein / 임베딩)
- `originallink` 우선, 없으면 `link` 사용

### 16.3 알림 품질
- 메시지 본문에 기자별 이모지 / 라벨
- 본문 자동 요약 (LLM 연동)
- 채널별 라우팅 (예: AI 키워드 → A 채널, 부동산 → B 채널)
- 긴 요약은 `disable_web_page_preview=false` 활용

### 16.4 운영 안정성
- 외부 DB 도입 (Supabase)
- 실패 기사 재시도 큐
- Slack / Discord 채널 동시 알림
- 오류 시 GitHub Issue 자동 등록
- 일일 실행 리포트 텔레그램 전송

---

## 17. MVP 완료 기준 (Definition of Done)

아래 10개 항목이 **모두 충족**되면 MVP 완료로 간주한다.

- [ ] GitHub Template Repository 로 복제 가능
- [ ] GitHub Secrets 5종 입력만으로 동작
- [ ] 여러 기자를 `REPORTERS` JSON 으로 자유 설정 가능
- [ ] 5분 cron 으로 GitHub Actions 자동 실행
- [ ] 네이버 검색 API 로 최신순 기사 수집
- [ ] 새 기사만 텔레그램 전송
- [ ] 전송 이력이 `data/sent_articles.json` 에 저장됨
- [ ] 동일 기사 재전송이 없음
- [ ] 새 기사 전송 후 이력 파일이 자동 커밋됨
- [ ] 비개발자가 README 만 보고 30분 안에 설치 가능

---

## 18. 위험 요소 및 완화책

| 위험 요소 | 영향 | 완화책 |
|---|---|---|
| GitHub cron 지연 / 누락 | 알림 지연 | 5분 간격은 "근사값" 임을 README 에 명시 |
| 네이버 API 무료 한도 초과 | 검색 실패 | 기자 50명 이하 권장, 한도 모니터링 |
| `sent_articles.json` 커밋 충돌 | 같은 기사 중복 전송 | concurrency + git pull --rebase |
| Bot 권한 부족 (채널) | 텔레그램 전송 실패 | 봇을 채널 관리자로 지정 안내 |
| GitHub 저장소가 Public 으로 노출 | Secrets 자체는 안전하나 일정 노출 | Private 저장소 권장 |
| 60일 무활동 cron 정지 | 봇이 침묵함 | 월 1회 자동 push (예: README 갱신 cron) |

---

## 19. 최종 제품 한 줄 설명

> **여러 기자의 새 기사를 약 5분 간격으로 자동 검사해, 아직 보낸 적 없는 기사만 텔레그램으로 보내주는 GitHub Actions 기반 무서버 알림봇.**
>
> GitHub 계정, 네이버 API 키, 텔레그램 봇 — 이 3가지만 있으면 비개발자도 30분 안에 시작할 수 있습니다.
