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

| Name | 필수 | Value |
|---|:---:|---|
| `NAVER_CLIENT_ID` | ✅ | Step 2 에서 받은 Client ID |
| `NAVER_CLIENT_SECRET` | ✅ | Step 2 에서 받은 Client Secret |
| `REPORTERS` | ✅ | 감시할 기자 목록 JSON (아래 5장 참고) |
| `TELEGRAM_BOT_TOKEN` | △ | Step 3 에서 받은 Bot Token |
| `TELEGRAM_CHAT_ID` | △ | Step 5 에서 확인한 chat_id |
| `LINE_CHANNEL_ACCESS_TOKEN` | △ | 라인으로 받을 때(아래 10장) |
| `LINE_GROUP_ID` | △ | 라인 그룹 ID(아래 10장) |

> **알림 채널은 텔레그램·라인 중 최소 하나**만 설정하면 됩니다(둘 다 설정하면 양쪽으로 전송). 텔레그램만 쓰면 LINE_* 는 생략, 라인만 쓰면 TELEGRAM_* 를 생략하세요.

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
    "name": "",
    "press": "",
    "include_keywords": ["엔씨소프트", "신작"],
    "exclude_keywords": ["부고", "인사"]
  }
]
```

> 마지막 항목처럼 `name` 을 비우면 **기자가 아니라 키워드만으로** 검색합니다. (예: "엔씨소프트 신작" 관련 기사 감시)

### 5.2 Secrets 입력용 한 줄 형식

```json
[{"name":"홍길동","press":"한국경제","include_keywords":["AI","반도체"],"exclude_keywords":["부고","인사"]},{"name":"","press":"","include_keywords":["엔씨소프트","신작"],"exclude_keywords":[]}]
```

### 5.3 필드 설명

| 필드 | 필수 | 설명 |
|---|:---:|---|
| `naver_journalist` | ◎ | 네이버 **기자ID**(예: `"030/38807"` 또는 기자페이지 URL). 지정 시 **가장 정확** — 아래 "기자ID 모드" 참고 |
| `name` | △ | 기자 이름. **이름으로만 검색**합니다. **비우면 키워드만으로 검색** |
| `press` | ❌ | 언론사명. 검색 모드에선 **출처 도메인 필터**에 사용(아래). 기자ID 모드에선 표시용 |
| `domain` | ❌ | 기사 출처 도메인(문자열 또는 배열). 예: `"mtn.co.kr"`. 지정 시 `press` 추론보다 **우선** (검색 모드에서만) |
| `include_keywords` | △ | **모든** 키워드가 제목/요약에 있어야 함 (AND). `name` 이 비어 있으면(검색 모드) 검색어로도 사용 |
| `exclude_keywords` | ❌ | **하나라도** 제목/요약에 있으면 제외 (NOT) |

> **◎ 기자ID 모드 (가장 정확, 권장):** `naver_journalist` 를 지정하면 네이버 **기자 구독 페이지**(바이라인으로 정확히 귀속된 기사 목록)에서 직접 가져옵니다. 키워드 검색의 한계(기자명이 기사 제목/요약에 없으면 못 찾음, 동명이인 혼입)가 없습니다.
> - 기자ID 찾는 법: 네이버 뉴스에서 기자 이름 클릭 → 기자 페이지 URL `https://media.naver.com/journalist/030/38807` 의 `030/38807` 부분.
> - 이 모드에서는 `name`/`include_keywords` 없이 `naver_journalist` 만으로도 동작하며, 도메인 필터는 적용되지 않습니다.
>
> **△ 검색 모드 (기자ID 없을 때):** 네이버 검색을 **이름(+포함 키워드)** 으로 하고, 기사 출처(`originallink`) **도메인이 일치할 때만** 통과시킵니다. `press`→도메인 기본 매핑 내장(예: `MTN`→`mtn.co.kr`, `전자신문`→`etnews.com`, `연합뉴스`→`yna.co.kr`); 없으면 `domain` 으로 직접 지정. 단, **기자명이 기사 제목/요약에 등장하지 않는 기자는 검색으로 잡히지 않습니다** — 이 경우 기자ID 모드를 쓰세요.
>
> 한 항목에 `naver_journalist`/`name`/`include_keywords` 가 **모두 없으면** 오류로 처리됩니다.

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
- **5분 cadence 는 워크플로우 내부 self-loop 로 보장**합니다. GitHub `schedule` 은 지연·누락이 잦아 5분을 못 지키므로, 한 번 시작된 job 이 약 5시간 50분 동안 5분 간격으로 반복 실행합니다. `schedule`(`2-59/5`)과 `workflow_dispatch` 는 루프가 끝났을 때 다음 루프를 이어서 시작시키는 "재시작 트리거" 역할만 합니다(동시성 그룹이 끊김 없이 이어받음).
  - 이 방식은 Actions 분을 많이 쓰므로 **Public 저장소(무료·무제한)** 를 전제로 합니다. Private 은 월 2,000분 한도라 5분 cadence 가 불가능합니다(간격을 늘리거나 유료 분이 필요).
  - 첫 가동/멈춤 시에는 Actions 탭에서 **Run workflow** 로 한 번 시작해 주세요.
- **마지막 실행 시각(`last_run_at`) 이후 발행된 기사만 전송**합니다. 매 실행이 끝나면 실행 시작 시각을 `data/sent_articles.json` 에 저장하고, 다음 실행은 그 시점 이후에 올라온 기사만 골라 보냅니다.
  - cron 이 몇 분 지연돼도 윈도우가 **실제 경과 시간만큼 자동으로 늘어나** 기사를 놓치지 않습니다. (고정 5분 윈도우의 한계 보완)
  - **첫 실행**(저장된 실행 시각이 없을 때)은 과거 기사 폭주를 막기 위해 `LOOKBACK_MINUTES`(기본 5분)만큼만 거슬러 봅니다. `LOOKBACK_MINUTES` Secret/환경변수로 조정 가능.
  - URL 중복 제거가 함께 동작하므로 경계에서 겹쳐도 같은 기사가 두 번 전송되지는 않습니다.
- **전송 이력은 최근 7일치만 보관**합니다. `data/sent_articles.json` 이 무한정 커지지 않도록 매 실행 시 `sent_at` 기준 7일 이전 항목을 정리합니다(추가 안전장치로 최대 5,000건 cap). 이력은 중복 전송 방지용인데, `last_run_at` 이후 발행분만 처리하므로 7일이면 충분합니다.
- 60일간 push 가 없으면 schedule 이 자동 비활성화될 수 있어요. self-loop 가 5분마다 이력을 커밋하므로 활동이 계속 발생해 사실상 멈추지 않습니다.

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

## 9. 라인(LINE) 그룹방으로 받기 (선택)

> 과거의 **LINE Notify 는 2025-03-31 종료**됐습니다. 현재는 **LINE Messaging API**(공식계정/봇)로만 자동 전송이 가능합니다.

### 9.1 설정 순서

1. [LINE Developers 콘솔](https://developers.line.biz) 로그인 → **Provider** 생성
2. **Messaging API 채널** 생성 (= LINE 공식계정 생성)
3. 채널 설정에서 **Channel access token (long-lived)** 발급 → `LINE_CHANNEL_ACCESS_TOKEN` Secret 으로 등록
4. **"Allow bot to join group chats"**(그룹 채팅 참여 허용) 를 **켜기**
5. 알림 받을 **라인 그룹방에 공식계정(봇) 초대**

### 9.2 `groupId` 확보 (한 번만)

`groupId` 는 웹훅 이벤트로만 얻을 수 있는데, 이 봇은 상시 서버가 없으므로 **일회성 캡처**가 필요합니다.

1. [webhook.site](https://webhook.site) 에 접속해 발급되는 고유 URL 복사
2. LINE 채널 설정 → **Webhook URL** 에 그 URL 붙여넣고 **Use webhook** 켜기
3. 봇이 들어와 있는 **그룹방에 아무 메시지나 한 번** 전송
4. webhook.site 로 들어온 JSON 에서 `"source": { "type": "group", "groupId": "Cxxxxx..." }` 의 `groupId` 복사
5. 그 값을 `LINE_GROUP_ID` Secret 으로 등록
6. (선택) 캡처가 끝나면 Webhook URL 은 비워도 됩니다 — 이후 전송은 push 라 웹훅이 필요 없습니다.

### 9.3 비용 한도 주의

- 무료 플랜은 **월 약 500건**(지역/플랜별 상이), 초과분은 유료.
- 메시지 수는 **받는 사람 수로 카운트** — 그룹 push 는 **그룹 인원수만큼 차감**될 수 있습니다(예: 30명 그룹 1회 = 30건). 큰 그룹은 한도 소진이 빠르니 유의하세요.

> 텔레그램·라인 Secret 을 둘 다 등록하면 **양쪽 모두로** 전송됩니다. 한 채널이라도 전송에 성공하면 발송 처리되어 중복 전송되지 않습니다.

---

## 10. 끊김 없는 5분 실행 (`DISPATCH_PAT`, 강력 권장)

self-loop 는 한 번에 약 5시간 50분만 돕니다. 다음 루프는 `schedule`(또는 수동 실행)이 이어줘야 하는데, GitHub `schedule` 은 지연이 심해 **루프 종료 후 최대 수 시간 공백**이 생길 수 있습니다(그 사이 발행 기사는 크게 지연).

이를 없애려면 루프가 끝날 때 **자기 자신을 곧바로 다시 트리거**하면 됩니다. 그런데 기본 `GITHUB_TOKEN` 은 보안상 새 워크플로우를 트리거하지 못하므로, **Actions 쓰기 권한이 있는 PAT** 가 필요합니다.

### 설정 순서

1. [Fine-grained PAT 생성](https://github.com/settings/personal-access-tokens/new)
   - **Resource owner**: 본인 계정, **Repository access**: `news-reporter-watcher` 만 선택
   - **Permissions → Repository permissions → Actions: Read and write**
   - (Contents 권한은 불필요) 생성 후 토큰 복사
2. 저장소 **Settings → Secrets → Actions** 에 `DISPATCH_PAT` 로 등록
3. 끝. 이후 루프가 끝날 때마다 즉시 다음 루프를 띄워(동시성 그룹이 이어받음) **공백 없이 24시간 5분 cadence** 가 유지됩니다.

> `DISPATCH_PAT` 가 없으면 `schedule` 에 의존하며 공백이 생길 수 있습니다(동작은 하되 실시간성이 떨어짐).

---

## 11. 라이선스

이 템플릿은 자유롭게 복사/수정/사용 가능합니다.
