"""
News Reporter Telegram Bot - Watcher
====================================

GitHub Actions에서 5분 간격으로 실행되어,
지정한 기자의 새 기사를 네이버 검색 API로 가져와 텔레그램으로 전송한다.

환경변수:
  NAVER_CLIENT_ID      네이버 개발자 센터 Client ID
  NAVER_CLIENT_SECRET  네이버 개발자 센터 Client Secret
  TELEGRAM_BOT_TOKEN   BotFather로 발급받은 봇 토큰(기본 채널)
  TELEGRAM_CHAT_ID     알림을 받을 채팅방/채널 ID(기본 채널, 쉼표 구분 다중 가능)
  TELEGRAM_CHANNELS    (선택) 기자별로 다른 봇/채팅방으로 보내기 위한 이름표 채널 목록(JSON 객체).
                       예: {"seo":{"bot_token":"...","chat_id":"-100...","reporters":["서정근"]}}
                       "reporters" 에 적힌 기자(또는 REPORTERS 항목의 "extra_channels" 로 이 키를
                       가리키는 기자)의 기사는 기본 채널에 더해 그 채널로도 함께 전송한다.
  REPORTERS            감시할 기자 목록(JSON 배열, 한 줄)
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests
from dateutil import parser as date_parser


# ---------------------------------------------------------------------------
# 상수 / 경로 설정
# ---------------------------------------------------------------------------

NAVER_NEWS_ENDPOINT = "https://openapi.naver.com/v1/search/news.json"
TELEGRAM_API_BASE = "https://api.telegram.org"
LINE_PUSH_ENDPOINT = "https://api.line.me/v2/bot/message/push"

# 네이버 '기자 구독' 페이지(바이라인 정확 귀속). {oid}=언론사코드, {jid}=기자ID.
NAVER_JOURNALIST_URL = "https://media.naver.com/journalist/{oid}/{jid}"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

ROOT_DIR = Path(__file__).resolve().parent
SENT_FILE = ROOT_DIR / "data" / "sent_articles.json"

MAX_HISTORY = 5000           # sent_articles.json 최대 보관 건수(시간 컷 이후의 안전장치)
MAX_HISTORY_DAYS = 7         # sent_at 기준 이 일수 이전 이력은 정리
SEARCH_DISPLAY = 50          # 네이버 검색 1회당 결과 수(이름 검색 + 도메인 필터라 넉넉히)
REQUEST_TIMEOUT = 10         # 외부 API 타임아웃(초)
TELEGRAM_RATE_LIMIT_SLEEP = 0.7  # 메시지 사이 대기(초)

# 평소에는 "마지막 실행 시각(last_run_at)" 이후 발행분만 처리한다.
# 저장된 실행 시각이 없는 첫 실행에서만, 과거 기사 폭주를 막기 위해
# 최근 이 분(分)만큼만 거슬러 본다. LOOKBACK_MINUTES 환경변수로 조정 가능.
DEFAULT_LOOKBACK_MINUTES = 5

# 네이버 색인 지연으로 누락되지 않도록 cutoff 를 이 분(分)만큼 앞당겨 겹쳐 본다.
# 특히 검색 모드(예: MTN)는 기사가 발행 후 수십 분~수 시간 뒤 검색 색인에 올라와,
# 그 시점엔 발행시각이 이미 cutoff 보다 과거가 되어 누락되던 문제가 있었다.
# 넉넉히 겹쳐도 URL 중복 제거가 재전송을 막으므로 안전하다.
OVERLAP_MINUTES = 240

# 언론사명 → 기사 출처 도메인 기본 매핑.
# reporter 에 "domain" 을 직접 지정하지 않았을 때 press 로부터 도메인을 추론한다.
# (검색은 이름으로 하고, 기사 originallink 의 도메인이 이 값과 일치할 때만 통과시킨다.)
PRESS_DOMAINS: dict[str, list[str]] = {
    "MTN": ["mtn.co.kr"],
    "머니투데이방송": ["mtn.co.kr"],
    "전자신문": ["etnews.com"],
    "연합뉴스": ["yna.co.kr"],
    "연합인포맥스": ["einfomax.co.kr"],
}

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 환경변수 / 설정 로딩
# ---------------------------------------------------------------------------

def env_required(name: str) -> str:
    """필수 환경변수를 읽어오고, 비어 있으면 오류를 낸다."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"[ERROR] 환경변수 '{name}' 가 설정되지 않았습니다.")
    return value


def parse_journalist(raw: Any) -> dict[str, str] | None:
    """naver_journalist 값에서 (oid, jid) 를 뽑는다.

    허용 형식: "030/38807", "030_38807", 또는 기자페이지 URL
    (예: https://media.naver.com/journalist/030/38807). 못 뽑으면 None.
    """
    if not raw:
        return None
    text = str(raw).strip()
    m = re.search(r"(\d{2,4})[/_](\d{2,})", text)
    if not m:
        return None
    return {"oid": m.group(1), "jid": m.group(2)}


def load_reporters(raw: str) -> list[dict[str, Any]]:
    """REPORTERS Secret(JSON 배열) 을 파싱/검증한다."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(
            f"[ERROR] REPORTERS JSON 파싱 실패: {e.msg} (line {e.lineno}, col {e.colno})"
        )

    if not isinstance(data, list) or not data:
        raise SystemExit("[ERROR] REPORTERS 는 비어있지 않은 JSON 배열이어야 합니다.")

    cleaned: list[dict[str, Any]] = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise SystemExit(f"[ERROR] REPORTERS[{idx}] 항목이 객체가 아닙니다.")
        name = str(item.get("name", "")).strip()
        press = str(item.get("press", "")).strip()
        include_keywords = [str(k).strip() for k in item.get("include_keywords", []) if str(k).strip()]
        exclude_keywords = [str(k).strip() for k in item.get("exclude_keywords", []) if str(k).strip()]
        journalist = parse_journalist(item.get("naver_journalist", ""))
        # 추가 알림 채널 이름표(문자열 또는 배열). 기본 채널에는 항상 보내고,
        # 여기 적힌 TELEGRAM_CHANNELS 항목으로도 '추가로' 함께 보낸다.
        extra_field = item.get("extra_channels", item.get("extra_channel", []))
        if isinstance(extra_field, str):
            extra_channels = [extra_field.strip()] if extra_field.strip() else []
        elif isinstance(extra_field, list):
            extra_channels = [str(c).strip() for c in extra_field if str(c).strip()]
        else:
            raise SystemExit(f"[ERROR] REPORTERS[{idx}].extra_channels 는 문자열 또는 배열이어야 합니다.")

        # 검색 모드라면(기자ID 없음) 검색어가 비지 않도록 name 또는 include_keywords 가
        # 하나는 필요하다. 기자ID 모드는 ID 로 직접 가져오므로 이 제약이 없다.
        if not journalist and not name and not include_keywords:
            raise SystemExit(
                f"[ERROR] REPORTERS[{idx}] 는 name/include_keywords/naver_journalist 중 하나가 필요합니다."
            )

        # 로그/메시지 표시 라벨: 이름 > 키워드 > press > 기자ID 순.
        if name:
            label = name
        elif include_keywords:
            label = " ".join(include_keywords)
        elif press:
            label = press
        else:
            label = f"기자 {journalist['oid']}/{journalist['jid']}"

        # 출처 도메인 필터. 기자ID 모드는 이미 바이라인으로 정확 귀속되므로 필터 없음.
        # 검색 모드에서는 "domain"(문자열/배열) 지정 우선, 없으면 press→PRESS_DOMAINS 추론.
        domains: list[str] = []
        if not journalist:
            domain_field = item.get("domain", [])
            if isinstance(domain_field, str):
                domains = [domain_field.strip().lower()] if domain_field.strip() else []
            elif isinstance(domain_field, list):
                domains = [str(d).strip().lower() for d in domain_field if str(d).strip()]
            if not domains and press:
                domains = [d.lower() for d in PRESS_DOMAINS.get(press, [])]

        cleaned.append({
            "name": name,
            "label": label,
            "press": press,
            "journalist": journalist,
            "domains": domains,
            "include_keywords": include_keywords,
            "exclude_keywords": exclude_keywords,
            "extra_channels": extra_channels,
        })
    return cleaned


# ---------------------------------------------------------------------------
# 네이버 검색
# ---------------------------------------------------------------------------

HTML_TAG_RE = re.compile(r"<[^>]+>")
HTML_ENTITY_MAP = {
    "&quot;": '"',
    "&apos;": "'",
    "&lt;": "<",
    "&gt;": ">",
    "&amp;": "&",
    "&#39;": "'",
    "&nbsp;": " ",
}


def strip_html(text: str) -> str:
    """네이버 응답의 <b>...</b> 강조 태그와 HTML 엔터티를 제거한다."""
    if not text:
        return ""
    text = HTML_TAG_RE.sub("", text)
    for k, v in HTML_ENTITY_MAP.items():
        text = text.replace(k, v)
    return text.strip()


def build_query(reporter: dict[str, Any]) -> str:
    """검색용 네이버 쿼리 문자열을 만든다.

    이름(+포함 키워드)만으로 검색한다. 언론사는 검색어에 넣지 않고
    기사 출처 도메인 필터(passes_domain)로 가린다. 바이라인 형식이
    매체마다 달라 '"{name} 기자"' 정확구문은 최신 기사를 놓치기 때문이다.
    """
    parts: list[str] = []
    if reporter.get("name"):
        parts.append(reporter["name"])
    parts.extend(reporter.get("include_keywords", []))
    return " ".join(parts)


def search_naver_news(query: str, client_id: str, client_secret: str) -> list[dict[str, Any]]:
    """네이버 뉴스 검색 API 호출. 실패 시 빈 리스트 반환."""
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    params = {
        "query": query,
        "display": SEARCH_DISPLAY,
        "start": 1,
        "sort": "date",
    }
    try:
        resp = requests.get(
            NAVER_NEWS_ENDPOINT,
            headers=headers,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            print(f"[WARN] 네이버 검색 실패 ({resp.status_code}): {resp.text[:200]}", file=sys.stderr)
            return []
        items = resp.json().get("items", [])
    except requests.RequestException as e:
        print(f"[WARN] 네이버 검색 요청 오류: {e}", file=sys.stderr)
        return []
    except json.JSONDecodeError:
        print("[WARN] 네이버 검색 응답 JSON 파싱 실패", file=sys.stderr)
        return []

    cleaned: list[dict[str, Any]] = []
    for it in items:
        cleaned.append({
            "title": strip_html(it.get("title", "")),
            "description": strip_html(it.get("description", "")),
            "originallink": (it.get("originallink") or "").strip(),
            "link": (it.get("link") or "").strip(),
            "pubDate": it.get("pubDate", ""),
        })
    return cleaned


# 기자 페이지의 기사 항목 1개를 파싱하기 위한 패턴들.
_JOURNALIST_LINK_RE = re.compile(r'href="(https://n\.news\.naver\.com/article/[^"]+)"')
_JOURNALIST_TITLE_RE = re.compile(r'press_edit_news_title[^>]*>\s*([^<]+?)\s*<')
_JOURNALIST_DATE_RE = re.compile(r'/(\d{4})/(\d{2})/(\d{2})/\d+\.(?:jpg|png|gif)', re.IGNORECASE)
# 네이버 기사 페이지의 실제 발행 시각(KST). 첫 매치가 발행시각, 둘째가 수정시각.
_ARTICLE_DATE_TIME_RE = re.compile(r'data-date-time="(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})"')


def fetch_article_published_at(url: str) -> str:
    """네이버 기사 페이지에서 실제 발행 시각(KST)을 ISO 문자열로 가져온다.

    기자 페이지는 날짜(일)만 알려주므로, 정확한 시:분:초는 기사 페이지에서 읽는다.
    실패 시 빈 문자열을 반환한다(호출부가 기존 값을 유지).
    """
    try:
        resp = requests.get(url, headers={"User-Agent": BROWSER_UA}, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return ""
        m = _ARTICLE_DATE_TIME_RE.search(resp.text)
    except requests.RequestException:
        return ""
    if not m:
        return ""
    y, mo, d, hh, mm, ss = m.groups()
    return f"{y}-{mo}-{d}T{hh}:{mm}:{ss}+09:00"


def fetch_journalist_articles(journalist: dict[str, str]) -> list[dict[str, Any]]:
    """네이버 기자 페이지에서 해당 기자의 최신 기사 목록을 가져온다.

    검색 API 와 동일한 형태(dict)로 반환한다. 발행 시각은 기사 썸네일 URL 의
    /YYYY/MM/DD/ 에서 날짜를 뽑아 그날 23:59:59 KST 로 둔다(당일 신규 기사가
    워터마크를 통과하도록). 정확 귀속이라 URL 중복 제거만으로 재전송이 막힌다.
    실패 시 빈 리스트를 반환한다.
    """
    # 기자 페이지는 CDN 에 ~15분 캐시되어(Age 헤더) 신규 기사 노출이 늦다.
    # 매 요청마다 바뀌는 cache-buster 쿼리 + no-cache 헤더로 원본 최신본을 받는다.
    base = NAVER_JOURNALIST_URL.format(oid=journalist["oid"], jid=journalist["jid"])
    url = f"{base}?cb={int(time.time())}"
    headers = {"User-Agent": BROWSER_UA, "Cache-Control": "no-cache", "Pragma": "no-cache"}
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            print(f"[WARN] 기자 페이지 요청 실패 ({resp.status_code}): {url}", file=sys.stderr)
            return []
        page = resp.text
    except requests.RequestException as e:
        print(f"[WARN] 기자 페이지 요청 오류: {e}", file=sys.stderr)
        return []

    articles: list[dict[str, Any]] = []
    # 기사 항목 단위로 쪼갠 뒤 각 조각에서 링크/제목/날짜를 뽑는다.
    chunks = page.split('class="press_edit_news_item')
    for chunk in chunks[1:]:
        link_m = _JOURNALIST_LINK_RE.search(chunk)
        title_m = _JOURNALIST_TITLE_RE.search(chunk)
        if not link_m or not title_m:
            continue
        link = link_m.group(1)
        title = html.unescape(title_m.group(1)).strip()

        date_m = _JOURNALIST_DATE_RE.search(chunk)
        if date_m:
            y, mo, d = date_m.group(1), date_m.group(2), date_m.group(3)
            pub_date = f"{y}-{mo}-{d}T23:59:59+09:00"
        else:
            # 날짜를 못 찾으면 오늘로 간주(과도한 누락 방지).
            pub_date = datetime.now(KST).strftime("%Y-%m-%dT23:59:59+09:00")

        articles.append({
            "title": title,
            "description": "",
            "originallink": link,
            "link": link,
            "pubDate": pub_date,
        })
    return articles


# ---------------------------------------------------------------------------
# 필터링 / 중복 제거
# ---------------------------------------------------------------------------

def passes_filters(article: dict[str, Any], reporter: dict[str, Any]) -> bool:
    """포함/제외 키워드 필터를 적용한다."""
    haystack = f"{article['title']} {article['description']}"
    haystack_lower = haystack.lower()

    for kw in reporter.get("include_keywords", []):
        if kw.lower() not in haystack_lower:
            return False
    for kw in reporter.get("exclude_keywords", []):
        if kw.lower() in haystack_lower:
            return False
    return True


def normalize_url(url: str) -> str:
    """query string / fragment / 공백을 제거한 정규화 URL 을 반환한다."""
    if not url:
        return ""
    url = url.strip()
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def article_id(url: str) -> str:
    """정규화한 URL 의 SHA-256 해시를 ID 로 사용한다."""
    norm = normalize_url(url)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def pick_url(article: dict[str, Any]) -> str:
    """originallink 우선, 없으면 link 사용."""
    return article.get("originallink") or article.get("link") or ""


def article_host(article: dict[str, Any]) -> str:
    """기사 출처 도메인(호스트)을 소문자로 반환한다.

    네이버가 감싼 link(n.news.naver.com)가 아닌 originallink(원 매체 URL)를
    우선 사용한다. originallink 가 없으면 link 로 대체한다.
    """
    url = article.get("originallink") or article.get("link") or ""
    try:
        host = urlsplit(url.strip()).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def passes_domain(article: dict[str, Any], reporter: dict[str, Any]) -> bool:
    """기사 출처 도메인이 reporter 의 지정 도메인과 일치하는지 검사한다.

    지정 도메인이 없으면(매핑 불가) 필터를 적용하지 않고 통과시킨다.
    'mtn.co.kr' 지정 시 'news.mtn.co.kr' 같은 서브도메인도 일치로 본다.
    """
    domains = reporter.get("domains", [])
    if not domains:
        return True
    host = article_host(article)
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in domains)


# ---------------------------------------------------------------------------
# 전송 이력 파일 I/O
# ---------------------------------------------------------------------------

def load_sent() -> dict[str, Any]:
    """data/sent_articles.json 로드. 파일이 없으면 빈 구조 반환."""
    if not SENT_FILE.exists():
        return {"sent": []}
    try:
        with SENT_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("sent"), list):
            print("[WARN] sent_articles.json 형식이 잘못되어 초기화합니다.", file=sys.stderr)
            return {"sent": []}
        return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"[WARN] sent_articles.json 로드 실패({e}). 초기화합니다.", file=sys.stderr)
        return {"sent": []}


def save_sent(sent_data: dict[str, Any]) -> None:
    """sent_at 기준 최근 MAX_HISTORY_DAYS 일치만 남기고 저장한다.

    시간 컷 이후에도 건수가 MAX_HISTORY 를 넘으면 최신 것부터 잘라낸다(안전장치).
    sent_at 을 파싱할 수 없는 항목은 보수적으로 유지한다(dedup 정합성 우선).
    """
    items = sent_data.get("sent", [])

    retention_cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_HISTORY_DAYS)
    kept = []
    for entry in items:
        sent_at = parse_datetime(entry.get("sent_at", ""))
        if sent_at is None or sent_at >= retention_cutoff:
            kept.append(entry)
    items = kept

    if len(items) > MAX_HISTORY:
        items = items[-MAX_HISTORY:]
    sent_data["sent"] = items

    SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SENT_FILE.open("w", encoding="utf-8") as f:
        json.dump(sent_data, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ---------------------------------------------------------------------------
# 알림 전송 (텔레그램 / 라인)
# ---------------------------------------------------------------------------

def parse_datetime(raw: str) -> datetime | None:
    """RFC822(pubDate) / ISO8601(last_run_at) 문자열을 aware datetime 으로 파싱.

    파싱 불가/빈 값이면 None 을 반환한다. tzinfo 가 없으면 UTC 로 간주한다.
    """
    if not raw:
        return None
    try:
        dt = date_parser.parse(raw)
    except (ValueError, TypeError, OverflowError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def format_published_at(pub_date_raw: str) -> str:
    """RFC822 형식의 pubDate 를 KST 'YYYY-MM-DD HH:MM' 으로 변환."""
    dt = parse_datetime(pub_date_raw)
    if dt is None:
        return pub_date_raw or "(시간 정보 없음)"
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M")


def is_after(article: dict[str, Any], cutoff: datetime) -> bool:
    """기사 발행 시각이 cutoff 이후(=마지막 실행 이후 신규)인지 판단한다.

    발행 시각을 파싱할 수 없으면 윈도우 밖으로 간주하여 제외한다.
    """
    dt = parse_datetime(article.get("pubDate", ""))
    if dt is None:
        return False
    return dt >= cutoff


def load_lookback_minutes() -> int:
    """LOOKBACK_MINUTES 환경변수를 읽는다(첫 실행 fallback 용). 미설정/이상값이면 기본값."""
    raw = os.environ.get("LOOKBACK_MINUTES", "").strip()
    if not raw:
        return DEFAULT_LOOKBACK_MINUTES
    try:
        value = int(raw)
    except ValueError:
        print(f"[WARN] LOOKBACK_MINUTES 값이 정수가 아님('{raw}'). 기본 {DEFAULT_LOOKBACK_MINUTES}분 사용.", file=sys.stderr)
        return DEFAULT_LOOKBACK_MINUTES
    if value <= 0:
        print(f"[WARN] LOOKBACK_MINUTES 가 0 이하({value}). 기본 {DEFAULT_LOOKBACK_MINUTES}분 사용.", file=sys.stderr)
        return DEFAULT_LOOKBACK_MINUTES
    return value


def format_message(article: dict[str, Any], reporter: dict[str, Any]) -> str:
    """알림 본문을 만든다(텔레그램/라인 공통 평문)."""
    url = pick_url(article)
    press_line = f"언론사: {reporter['press']}\n" if reporter.get("press") else ""
    summary = article.get("description", "").strip()
    if len(summary) > 350:
        summary = summary[:347] + "..."

    # name 이 있으면 '홍길동 기자', 없으면 키워드 라벨을 헤더로 쓴다.
    header = f"{reporter['name']} 기자" if reporter.get("name") else reporter.get("label", "키워드 검색")

    return (
        f"[새 기사] {header}\n\n"
        f"{press_line}"
        f"제목: {article['title']}\n"
        f"시간: {format_published_at(article.get('pubDate', ''))}\n"
        f"링크: {url}\n\n"
        f"{summary}"
    )


def send_telegram(message: str, bot_token: str, chat_id: str) -> bool:
    """텔레그램 메시지를 전송한다. 성공 여부 반환."""
    url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            print(f"[WARN] 텔레그램 전송 실패 ({resp.status_code}): {resp.text[:200]}", file=sys.stderr)
            return False
        return True
    except requests.RequestException as e:
        print(f"[WARN] 텔레그램 요청 오류: {e}", file=sys.stderr)
        return False


def send_line(message: str, channel_access_token: str, target_id: str) -> bool:
    """LINE Messaging API 로 push 메시지를 보낸다. 성공 여부 반환.

    target_id 는 그룹(groupId)/다자대화(roomId)/사용자(userId) 중 하나.
    봇(공식계정)이 해당 그룹에 초대돼 있어야 한다.
    """
    headers = {
        "Authorization": f"Bearer {channel_access_token}",
        "Content-Type": "application/json",
    }
    # LINE 텍스트 메시지는 최대 5000자.
    text = message if len(message) <= 5000 else message[:4997] + "..."
    payload = {"to": target_id, "messages": [{"type": "text", "text": text}]}
    try:
        resp = requests.post(LINE_PUSH_ENDPOINT, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            print(f"[WARN] 라인 전송 실패 ({resp.status_code}): {resp.text[:200]}", file=sys.stderr)
            return False
        return True
    except requests.RequestException as e:
        print(f"[WARN] 라인 요청 오류: {e}", file=sys.stderr)
        return False


Notifier = tuple[str, Any]  # (표시 이름, message -> bool 전송함수)


def make_notifiers(
    tg_token: str,
    tg_chat_ids: str,
    line_token: str = "",
    line_group: str = "",
    prefix: str = "",
) -> list[Notifier]:
    """토큰/대상 값으로 (이름, 전송함수) 목록을 만든다. 값이 비면 해당 항목은 생략.

    tg_chat_ids 는 쉼표로 여러 대상(그룹/채널/DM)을 지정할 수 있다.
    예: "-1004371006208,-1001234567890"
    prefix 는 로그 표시용 이름표(예: "seo:") — 기본 채널은 빈 문자열.
    """
    notifiers: list[Notifier] = []

    tg_token = (tg_token or "").strip()
    tg_chats = [c.strip() for c in (tg_chat_ids or "").split(",") if c.strip()]
    if tg_token and tg_chats:
        for chat in tg_chats:
            label = f"{prefix}Telegram" if len(tg_chats) == 1 else f"{prefix}Telegram({chat})"
            notifiers.append((label, lambda m, c=chat, t=tg_token: send_telegram(m, t, c)))

    line_token = (line_token or "").strip()
    line_group = (line_group or "").strip()
    if line_token and line_group:
        notifiers.append((f"{prefix}LINE", lambda m, t=line_token, g=line_group: send_line(m, t, g)))

    return notifiers


def build_notifiers() -> list[Notifier]:
    """기본 알림 채널(환경변수 TELEGRAM_*/LINE_*)의 전송함수 목록을 만든다.

    - 텔레그램: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID 가 모두 있을 때.
    - 라인:     LINE_CHANNEL_ACCESS_TOKEN + LINE_GROUP_ID 가 모두 있을 때
    하나도 없으면 오류로 종료한다(모든 기자의 기사는 항상 기본 채널로 나간다).
    """
    notifiers = make_notifiers(
        os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        os.environ.get("TELEGRAM_CHAT_ID", ""),
        os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", ""),
        os.environ.get("LINE_GROUP_ID", ""),
    )
    if not notifiers:
        raise SystemExit(
            "[ERROR] 알림 채널이 없습니다. (TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID) 또는 "
            "(LINE_CHANNEL_ACCESS_TOKEN+LINE_GROUP_ID) 중 하나 이상을 설정하세요."
        )
    return notifiers


def load_channels(raw: str) -> dict[str, dict[str, Any]]:
    """TELEGRAM_CHANNELS(JSON 객체) 를 파싱해 이름표별 {notifiers, reporters} 로 만든다.

    형식:
      {
        "seo":  {"bot_token": "712...:AAH...", "chat_id": "-1001234567890",
                 "reporters": ["서정근"]},
        "desk": {"bot_token": "...", "chat_id": "-100111,-100222",
                 "line_token": "...", "line_group_id": "C..."}
      }
    기자와 채널을 잇는 방법은 두 가지이며 둘 다 쓸 수 있다(합집합):
      - 채널 쪽 "reporters": 기자 이름(name) 또는 표시 라벨(label) 목록. REPORTERS 를 안 고쳐도 된다.
      - REPORTERS 항목 쪽 "extra_channels": 채널 이름표 목록.
    어느 쪽이든 매칭된 기자의 기사는 기본 채널에 더해 해당 채널로도 함께 전송된다.
    비어 있으면 빈 dict. 형식 오류나 토큰/대상이 빈 항목은 오류로 종료한다(조용히 누락되지 않도록).
    """
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(
            f"[ERROR] TELEGRAM_CHANNELS JSON 파싱 실패: {e.msg} (line {e.lineno}, col {e.colno})"
        )
    if not isinstance(data, dict):
        raise SystemExit('[ERROR] TELEGRAM_CHANNELS 는 JSON 객체여야 합니다. 예: {"seo":{"bot_token":"...","chat_id":"..."}}')

    channels: dict[str, dict[str, Any]] = {}
    for key, cfg in data.items():
        name = str(key).strip()
        if not name:
            raise SystemExit("[ERROR] TELEGRAM_CHANNELS 의 채널 이름(키)이 비어 있습니다.")
        if not isinstance(cfg, dict):
            raise SystemExit(f"[ERROR] TELEGRAM_CHANNELS['{name}'] 은 객체여야 합니다.")
        rep_field = cfg.get("reporters", [])
        if isinstance(rep_field, str):
            rep_names = [rep_field.strip()] if rep_field.strip() else []
        elif isinstance(rep_field, list):
            rep_names = [str(x).strip() for x in rep_field if str(x).strip()]
        else:
            raise SystemExit(f"[ERROR] TELEGRAM_CHANNELS['{name}'].reporters 는 문자열 또는 배열이어야 합니다.")
        notifiers = make_notifiers(
            str(cfg.get("bot_token", "") or ""),
            str(cfg.get("chat_id", "") or ""),
            str(cfg.get("line_token", "") or ""),
            str(cfg.get("line_group_id", "") or ""),
            prefix=f"{name}:",
        )
        if not notifiers:
            raise SystemExit(
                f"[ERROR] TELEGRAM_CHANNELS['{name}'] 에 유효한 대상이 없습니다. "
                "bot_token+chat_id (또는 line_token+line_group_id) 를 채우세요."
            )
        channels[name] = {"notifiers": notifiers, "reporters": rep_names}
    return channels


def resolve_notifiers(reporters: list[dict[str, Any]]) -> list[list[Notifier]]:
    """기자별 전송함수 목록을 reporters 와 같은 순서로 돌려준다.

    모든 기자는 기본 채널(TELEGRAM_*/LINE_*)로 보내고, 다음 중 하나로 연결된
    TELEGRAM_CHANNELS 항목이 있으면 그 채널로도 '추가로' 보낸다.
      - 채널의 "reporters" 에 기자 name 또는 label 이 들어 있음
      - 기자의 "extra_channels" 에 채널 이름표가 들어 있음
    가리키는 채널/기자가 없으면(오타 등) 시작 시점에 오류로 종료한다.
    각 기자의 실제 추가 채널 목록은 r["extra_channels"] 에 다시 채워 넣는다(로그/이력용).
    """
    default = build_notifiers()
    channels = load_channels(os.environ.get("TELEGRAM_CHANNELS", ""))

    # 채널 쪽 reporters 가 실제 기자를 가리키는지 검증(오타로 조용히 빠지지 않도록).
    known_names = {r["name"] for r in reporters if r.get("name")} | {r["label"] for r in reporters}
    for key, ch in channels.items():
        for rep in ch["reporters"]:
            if rep not in known_names:
                raise SystemExit(
                    f"[ERROR] TELEGRAM_CHANNELS['{key}'].reporters 의 '{rep}' 에 해당하는 기자가 REPORTERS 에 없습니다. "
                    f"기자 목록: {', '.join(sorted(known_names))}"
                )

    per_reporter: list[list[Notifier]] = []
    for r in reporters:
        keys: list[str] = []
        for key in r.get("extra_channels", []):
            if key not in channels:
                known = ", ".join(sorted(channels)) or "(없음)"
                raise SystemExit(
                    f"[ERROR] '{r['label']}' 의 extra_channels '{key}' 가 TELEGRAM_CHANNELS 에 없습니다. "
                    f"정의된 채널: {known}"
                )
            keys.append(key)
        for key, ch in channels.items():
            if key not in keys and (r.get("name") in ch["reporters"] or r["label"] in ch["reporters"]):
                keys.append(key)

        r["extra_channels"] = keys
        notifiers = list(default)
        for key in keys:
            notifiers.extend(channels[key]["notifiers"])
        per_reporter.append(notifiers)
    return per_reporter


def describe_notifiers(notifiers: list[Notifier]) -> str:
    return ", ".join(name for name, _ in notifiers)


# ---------------------------------------------------------------------------
# 메인 흐름
# ---------------------------------------------------------------------------

def selftest() -> int:
    """SELFTEST 환경변수가 있으면, 설정된 모든 알림 채널로 테스트 메시지를 보내고
    채널별 성공 여부를 출력한 뒤 종료한다(LINE/텔레그램 연동 진단용)."""
    print(f"[SELFTEST] === 알림 채널 자가진단: {datetime.now(KST).isoformat()} ===")
    # 기본 채널 + TELEGRAM_CHANNELS 의 이름표 채널 전부에 테스트 메시지를 보낸다.
    notifiers: list[Notifier] = []
    try:
        notifiers.extend(build_notifiers())
    except SystemExit as e:
        print(f"[SELFTEST] 기본 채널 오류: {e}")
    try:
        for name, chan in load_channels(os.environ.get("TELEGRAM_CHANNELS", "")).items():
            notifiers.extend(chan["notifiers"])
    except SystemExit as e:
        print(f"[SELFTEST] TELEGRAM_CHANNELS 오류: {e}")
    if not notifiers:
        print("[SELFTEST] 감지된 채널이 없습니다(TELEGRAM_*/LINE_*/TELEGRAM_CHANNELS 미설정).")
    else:
        print(f"[SELFTEST] 감지된 채널: {describe_notifiers(notifiers)}")
    msg = f"[자가진단] 워치맨 알림 테스트 — {datetime.now(KST).strftime('%Y-%m-%d %H:%M')} KST. 이 메시지가 보이면 해당 채널 연동 정상."
    for name, fn in notifiers:
        ok = fn(msg)
        print(f"[SELFTEST] {name}: {'성공' if ok else '실패'}")

    # 기자 설정 진단: 각 기자가 실제로 몇 건 잡히는지(검색/도메인/기자ID) 점검.
    try:
        reporters = load_reporters(os.environ.get("REPORTERS", ""))
        naver_id = os.environ.get("NAVER_CLIENT_ID", "").strip()
        naver_secret = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
        print(f"[SELFTEST] 기자 {len(reporters)}명: {', '.join(r['label'] for r in reporters)}")
        # 기자 → 채널 매핑 점검(없는 채널을 가리키면 여기서 오류 메시지가 나온다).
        try:
            for r, ns in zip(reporters, resolve_notifiers(reporters)):
                extra = f" (+{', '.join(r['extra_channels'])})" if r.get("extra_channels") else ""
                print(f"[SELFTEST]   {r['label']} → 기본 채널{extra} [{describe_notifiers(ns)}]")
        except SystemExit as e:
            print(f"[SELFTEST] 채널 매핑 오류: {e}")
        for r in reporters:
            if r.get("journalist"):
                arts = fetch_journalist_articles(r["journalist"])
                print(f"[SELFTEST]   {r['label']} (기자ID {r['journalist']['oid']}/{r['journalist']['jid']}): {len(arts)}건")
            else:
                q = build_query(r)
                arts = search_naver_news(q, naver_id, naver_secret)
                dom = sum(1 for a in arts if passes_domain(a, r))
                newest = arts[0]["pubDate"] if arts else "-"
                print(f"[SELFTEST]   {r['label']} (검색 '{q}', domains={r['domains']}): 검색 {len(arts)}건 / 도메인일치 {dom}건 / 최신 {newest}")
    except Exception as e:  # noqa: BLE001
        print(f"[SELFTEST] 기자 진단 오류: {e}")
    return 0


def main() -> int:
    print(f"[INFO] === Watcher 시작: {datetime.now(KST).isoformat()} ===")

    if os.environ.get("SELFTEST", "").strip():
        return selftest()

    naver_id = env_required("NAVER_CLIENT_ID")
    naver_secret = env_required("NAVER_CLIENT_SECRET")
    reporters_raw = env_required("REPORTERS")

    reporters = load_reporters(reporters_raw)
    # 기자별 알림 채널: 모두 기본 채널 + extra_channels 로 지정한 TELEGRAM_CHANNELS 항목 추가.
    notifiers_per_reporter = resolve_notifiers(reporters)
    print(f"[INFO] 기본 알림 채널: {describe_notifiers(build_notifiers())}")
    for r, ns in zip(reporters, notifiers_per_reporter):
        if r.get("extra_channels"):
            print(f"[INFO] '{r['label']}' 추가 채널: {', '.join(r['extra_channels'])} → 전송 대상 [{describe_notifiers(ns)}]")
    print(f"[INFO] {len(reporters)}명의 기자 감시 시작")

    sent_data = load_sent()
    seen_ids: set[str] = {entry.get("id", "") for entry in sent_data.get("sent", [])}

    # 이번 실행 시작 시각. 다음 실행의 cutoff 로 저장한다.
    # (fetch 도중 올라온 기사도 다음 실행에서 빠짐없이 포착하도록 '시작' 시각을 쓴다.)
    run_started_at = datetime.now(timezone.utc)

    last_run_at = parse_datetime(sent_data.get("last_run_at", ""))
    if last_run_at is None:
        # 첫 실행: 저장된 실행 시각이 없으므로 과거 기사 폭주를 막기 위해 fallback 윈도우 사용.
        lookback_minutes = load_lookback_minutes()
        cutoff = run_started_at - timedelta(minutes=lookback_minutes)
        print(f"[INFO] 첫 실행 — 최근 {lookback_minutes}분 이내 발행분만 처리 "
              f"(cutoff: {cutoff.astimezone(KST).strftime('%Y-%m-%d %H:%M')} KST)")
    else:
        # 색인 지연 대비로 OVERLAP_MINUTES 만큼 앞당겨 겹쳐 본다(중복은 dedup 이 차단).
        cutoff = last_run_at - timedelta(minutes=OVERLAP_MINUTES)
        print(f"[INFO] 마지막 실행({last_run_at.astimezone(KST).strftime('%Y-%m-%d %H:%M')} KST) 이후 발행분만 처리 "
              f"(겹침 {OVERLAP_MINUTES}분 적용 cutoff: {cutoff.astimezone(KST).strftime('%Y-%m-%d %H:%M')} KST)")

    total_sent = 0
    total_skipped = 0
    total_filtered = 0
    total_old = 0
    total_offsite = 0

    for reporter, notifiers in zip(reporters, notifiers_per_reporter):
        journalist = reporter.get("journalist")
        if journalist:
            print(f"[INFO] '{reporter['label']}' 기자페이지: {journalist['oid']}/{journalist['jid']}")
            articles = fetch_journalist_articles(journalist)
        else:
            query = build_query(reporter)
            print(f"[INFO] '{reporter['label']}' 검색 쿼리: {query}")
            articles = search_naver_news(query, naver_id, naver_secret)

        if not articles:
            print(f"[INFO]   결과 없음 또는 검색 실패. 다음 기자로 진행.")
            continue

        for article in articles:
            url = pick_url(article)
            if not url:
                continue

            # 중복 제거를 가장 먼저(가장 싸고, 이미 보낸 기사는 시각 보강도 불필요).
            aid = article_id(url)
            if aid in seen_ids:
                total_skipped += 1
                continue

            if not passes_domain(article, reporter):
                total_offsite += 1
                continue

            # 1차 시간 필터(기자 모드는 날짜 단위 coarse). 통과한 신규 기사만 다음 단계로.
            if not is_after(article, cutoff):
                total_old += 1
                continue

            # 기자 모드: 기사 페이지에서 실제 발행 시각을 보강한 뒤 정밀 재확인.
            if reporter.get("journalist"):
                real_time = fetch_article_published_at(article.get("link", url))
                if real_time:
                    article["pubDate"] = real_time
                    if not is_after(article, cutoff):
                        total_old += 1
                        continue

            if not passes_filters(article, reporter):
                total_filtered += 1
                continue

            message = format_message(article, reporter)
            results = [(name, fn(message)) for name, fn in notifiers]
            # 한 채널이라도 성공하면 발송 처리(중복 방지). 전부 실패하면 다음 실행에서 재시도.
            if not any(ok for _, ok in results):
                continue

            seen_ids.add(aid)
            sent_data["sent"].append({
                "id": aid,
                "reporter": reporter["label"],
                "press": reporter.get("press", ""),
                "extra_channels": reporter.get("extra_channels", []),
                "title": article["title"],
                "url": url,
                "published_at": article.get("pubDate", ""),
                "sent_at": datetime.now(KST).isoformat(),
            })
            total_sent += 1
            time.sleep(TELEGRAM_RATE_LIMIT_SLEEP)

    # 다음 실행이 이 시점 이후 기사만 보도록 실행 시작 시각을 저장한다.
    # (검색 실패 등으로 기사를 못 받았더라도 watermark 는 전진시켜, 같은 구간을
    #  반복 검색하지 않는다. 경계의 중복은 URL 해시 dedup 이 막아준다.)
    sent_data["last_run_at"] = run_started_at.isoformat()
    save_sent(sent_data)

    print(
        f"[INFO] === 완료 — 전송: {total_sent}건, "
        f"중복 스킵: {total_skipped}건, "
        f"마지막 실행 이전(오래됨): {total_old}건, "
        f"타사/도메인 불일치: {total_offsite}건, "
        f"필터 제외: {total_filtered}건 ==="
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
