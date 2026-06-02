# 기자 기사 텔레그램 알림봇 (GitHub Actions 기반)

지정한 기자의 새 기사를 **5분마다 자동으로** 확인해, 새 기사만 **텔레그램으로 즉시** 보내주는 알림봇입니다.

별도의 서버나 호스팅 비용이 필요 없습니다. **GitHub 계정 하나만 있으면** 누구나 사용할 수 있습니다.

> 본 저장소는 **GitHub Template Repository** 입니다. 코드 수정 없이 그대로 사용할 수 있습니다.

---

## 1. 이 봇이 하는 일

- 여러 기자의 새 기사를 동시에 감시
- 기자별로 언론사 / 포함 키워드 / 제외 키워드 지정 가능
- 5분 간격 자동 실행
- 이미 보낸 기사는 절대 다시 보내지 않음
- 메시지에 언론사, 기자명, 제목, 발행 시간, 링크, 요약 포함

---

## 2. 미리 준비할 것 (5분 소요)

| 준비물 | 비용 | 비고 |
|---|---|---|
| GitHub 계정 | 무료 | github.com 가입 |
| 네이버 개발자 센터 애플리케이션 | 무료 | API 호출 25,000건/일 |
| 텔레그램 계정 | 무료 | 모바일/PC 모두 가능 |
| 알림을 받을 채팅방 또는 채널 | 무료 | 개인 채팅도 가능 |

---

## 3. 설치 흐름 (9단계)

```text
1. Use this template 으로 저장소 복사
2. 새 저장소를 Private 으로 생성
3. 네이버 개발자 센터에서 API 키 발급
4. Telegram BotFather 에서 봇 생성
5. 봇을 알림 받을 채팅방/채널에 초대
6. chat_id 확인
7. GitHub Secrets 5개 입력
8. Actions 탭에서 워크플로우 활성화
9. Run workflow 로 첫 실행 테스트
```

---

## 4. 단계별 상세 가이드

### Step 1. 템플릿 저장소 복사

1. 본 저장소 페이지 상단의 초록색 **`Use this template`** 버튼 클릭
2. **`Create a new repository`** 선택
3. Repository name 자유 지정 (예: `my-news-watcher`)
4. **Private** 선택을 권장 (Secrets 보호 차원)
5. **`Create repository`** 클릭

### Step 2. 네이버 검색 API 키 발급

1. [네이버 개발자 센터](https://developers.naver.com) 접속 → 로그인
2. 상단 **`Application`** → **`애플리케이션 등록`** 클릭
3. 애플리케이션 이름 입력 (예: `news-watcher`)
4. **사용 API** 에서 **`검색`** 체크
5. **비로그인 오픈 API 서비스 환경** → **`WEB 설정`** 선택, URL 은 `https://github.com` 입력
6. 등록 후 표시되는 **Client ID** 와 **Client Secret** 을 메모장에 복사

### Step 3. Telegram 봇 생성

1. 텔레그램에서 **`@BotFather`** 와 대화 시작
2. 명령어 `/newbot` 전송
3. 봇 이름 입력 (자유)
4. 봇 username 입력 (예: `my_news_watcher_bot`, 끝이 `bot` 으로 끝나야 함)
5. BotFather 가 알려주는 **HTTP API Token** 복사
   - 형식 예: `7123456789:AAH...` (콜론 `:` 포함)

### Step 4. 봇을 채팅방/채널에 초대

**개인 채팅으로 받기**:
1. 위에서 만든 봇과 1:1 채팅 시작
2. 봇에게 아무 메시지(`/start` 등) 한 번 전송

**그룹/채널로 받기**:
1. 그룹/채널 생성
2. 봇을 멤버 또는 관리자로 초대
3. **채널이면 봇을 관리자(Admin)** 로 지정해야 메시지 전송 가능

### Step 5. chat_id 확인

가장 쉬운 방법: **`@userinfobot`** 또는 **`@RawDataBot`** 사용

- **개인 채팅 chat_id**: `@userinfobot` 에게 `/start` → 표시되는 `Id` 값
- **그룹/채널 chat_id**: 봇이 속한 그룹에 `@RawDataBot` 초대 → `/start` → `chat.id` 값
  - 채널은 보통 `-100` 으로 시작 (예: `-1001234567890`)

### Step 6. GitHub Secrets 입력 (가장 중요)

1. Step 1 에서 만든 저장소로 이동
2. **Settings → Secrets and variables → Actions** 메뉴 진입
3. **`New repository secret`** 버튼으로 아래 5개를 차례로 등록

| Name | Value |
|---|---|
| `NAVER_CLIENT_ID` | Step 2 에서 받은 Client ID |
| `NAVER_CLIENT_SECRET` | Step 2 에서 받은 Client Secret |
| `TELEGRAM_BOT_TOKEN` | Step 3 에서 받은 Bot Token |
| `TELEGRAM_CHAT_ID` | Step 5 에서 확인한 chat_id |
| `REPORTERS` | 감시할 기자 목록 JSON (아래 5장 참고) |

### Step 7. Actions 활성화

1. 저장소 상단 **`Actions`** 탭 클릭
2. 처음이라면 **`I understand my workflows, go ahead and enable them`** 버튼 클릭

### Step 8. 첫 실행 테스트

1. Actions 탭 좌측에서 **`Watch reporter news`** 워크플로우 선택
2. 우측 **`Run workflow`** → **`Run workflow`** 클릭
3. 1~2분 후 로그 확인 (초록 체크 ✅ 가 뜨면 성공)
4. 텔레그램에 알림이 도착하면 설치 완료

### Step 9. 자동 실행 확인

이후에는 GitHub Actions 가 **5분마다 자동으로 실행**됩니다. 별도 조작이 필요 없습니다.

---

## 5. REPORTERS 설정 작성법

`REPORTERS` Secret 은 **JSON 배열** 형식이며, GitHub Secrets 에는 **한 줄**로 붙여 넣어야 합니다.

### 5.1 보기 좋은 형식 (참고용)

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

### 5.2 Secrets 입력용 한 줄 형식

```json
[{"name":"홍길동","press":"한국경제","include_keywords":["AI","반도체"],"exclude_keywords":["부고","인사"]},{"name":"김철수","press":"매일경제","include_keywords":["스타트업","투자"],"exclude_keywords":[]}]
```

### 5.3 필드 설명

| 필드 | 필수 | 설명 |
|---|:---:|---|
| `name` | ✅ | 기자 이름. 검색어에 자동으로 "기자" 키워드가 붙음 |
| `press` | ❌ | 언론사명. 빈 문자열이면 언론사 제한 없음 |
| `include_keywords` | ❌ | **모든** 키워드가 제목/요약에 있어야 함 (AND) |
| `exclude_keywords` | ❌ | **하나라도** 제목/요약에 있으면 제외 (NOT) |

---

## 6. 자주 묻는 질문 (FAQ)

| 증상 | 원인 | 해결 |
|---|---|---|
| Actions 가 자동 실행되지 않음 | 워크플로우 비활성화, 60일 무활동으로 cron 정지 | Actions 탭에서 활성화, Run workflow 1회 실행 |
| 텔레그램 메시지가 안 옴 | Bot Token / chat_id 오류, 봇이 채널 관리자가 아님 | Secrets 재확인, 봇 권한 확인 |
| 네이버 검색 결과가 비어 있음 | Client ID/Secret 오타, 일일 한도 초과 | 네이버 개발자 센터에서 키 재확인 |
| 같은 기사가 반복 수신 | `sent_articles.json` 커밋 실패 | Actions 로그의 commit 단계 확인 |
| 새 기사가 전혀 안 옴 | `include_keywords` 가 너무 좁음 | 키워드 줄이거나 제거 |
| `Bad credentials` 로그 | Secrets 누락 | 5개가 모두 등록됐는지 확인 |

---

## 7. 운영 시 알아둘 점

- **네이버 API 일일 한도**는 25,000건. 기자 50명 이하 권장.
- GitHub Actions cron 은 **UTC 기준**이지만 5분 간격이라 시간대 영향 없음.
- "5분 간격"은 정확한 5분 0초 보장이 아닙니다. GitHub 인프라 상황에 따라 지연될 수 있습니다.
- 60일간 push 가 없으면 cron 이 자동 비활성화될 수 있어요. 가끔 Run workflow 를 눌러주세요.
- Public 저장소: cron 무료/무제한. Private 저장소: 월 2,000분 무료 한도 내에서 사용.

---

## 8. 로컬 테스트 (선택 사항, 개발자용)

```bash
export NAVER_CLIENT_ID="..."
export NAVER_CLIENT_SECRET="..."
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
export REPORTERS='[{"name":"홍길동","press":"한국경제","include_keywords":[],"exclude_keywords":[]}]'

pip install -r requirements.txt
python watcher.py
```

---

## 9. 라이선스

이 템플릿은 자유롭게 복사/수정/사용 가능합니다.
