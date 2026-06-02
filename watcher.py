"""
News Reporter Telegram Bot - Watcher
====================================

GitHub Actions에서 5분 간격으로 실행되어,
지정한 기자의 새 기사를 네이버 검색 API로 가져와 텔레그램으로 전송한다.

환경변수:
  NAVER_CLIENT_ID      네이버 개발자 센터 Client ID
  NAVER_CLIENT_SECRET  네이버 개발자 센터 Client Secret
  TELEGRAM_BOT_TOKEN   BotFather로 발급받은 봇 토큰
  TELEGRAM_CHAT_ID     알림을 받을 채팅방/채널 ID
  REPORTERS            감시할 기자 목록(JSON 배열, 한 줄)
"""

from __future__ import annotations

import hashlib
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

ROOT_DIR = Path(__file__).resolve().parent
SENT_FILE = ROOT_DIR / "data" / "sent_articles.json"

MAX_HISTORY = 5000           # sent_articles.json 최대 보관 건수
SEARCH_DISPLAY = 20          # 네이버 검색 1회당 결과 수
REQUEST_TIMEOUT = 10         # 외부 API 타임아웃(초)
TELEGRAM_RATE_LIMIT_SLEEP = 0.7  # 메시지 사이 대기(초)

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
        if not name:
            raise SystemExit(f"[ERROR] REPORTERS[{idx}].name 이 비어있습니다.")
        cleaned.append({
            "name": name,
            "press": str(item.get("press", "")).strip(),
            "include_keywords": [str(k).strip() for k in item.get("include_keywords", []) if str(k).strip()],
            "exclude_keywords": [str(k).strip() for k in item.get("exclude_keywords", []) if str(k).strip()],
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
    """기자 검색용 네이버 쿼리 문자열을 만든다."""
    parts: list[str] = [f'"{reporter["name"]} 기자"']
    if reporter.get("press"):
        parts.append(reporter["press"])
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
    """최근 MAX_HISTORY 건만 남기고 저장한다."""
    items = sent_data.get("sent", [])
    if len(items) > MAX_HISTORY:
        items = items[-MAX_HISTORY:]
    sent_data["sent"] = items

    SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SENT_FILE.open("w", encoding="utf-8") as f:
        json.dump(sent_data, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ---------------------------------------------------------------------------
# 텔레그램 전송
# ---------------------------------------------------------------------------

def format_published_at(pub_date_raw: str) -> str:
    """RFC822 형식의 pubDate 를 KST 'YYYY-MM-DD HH:MM' 으로 변환."""
    if not pub_date_raw:
        return "(시간 정보 없음)"
    try:
        dt = date_parser.parse(pub_date_raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return pub_date_raw


def format_message(article: dict[str, Any], reporter: dict[str, Any]) -> str:
    """텔레그램 본문을 만든다."""
    url = pick_url(article)
    press_line = f"언론사: {reporter['press']}\n" if reporter.get("press") else ""
    summary = article.get("description", "").strip()
    if len(summary) > 350:
        summary = summary[:347] + "..."

    return (
        f"[새 기사] {reporter['name']} 기자\n\n"
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


# ---------------------------------------------------------------------------
# 메인 흐름
# ---------------------------------------------------------------------------

def main() -> int:
    print(f"[INFO] === Watcher 시작: {datetime.now(KST).isoformat()} ===")

    naver_id = env_required("NAVER_CLIENT_ID")
    naver_secret = env_required("NAVER_CLIENT_SECRET")
    bot_token = env_required("TELEGRAM_BOT_TOKEN")
    chat_id = env_required("TELEGRAM_CHAT_ID")
    reporters_raw = env_required("REPORTERS")

    reporters = load_reporters(reporters_raw)
    print(f"[INFO] {len(reporters)}명의 기자 감시 시작")

    sent_data = load_sent()
    seen_ids: set[str] = {entry.get("id", "") for entry in sent_data.get("sent", [])}

    total_sent = 0
    total_skipped = 0
    total_filtered = 0

    for reporter in reporters:
        query = build_query(reporter)
        print(f"[INFO] '{reporter['name']}' 검색 쿼리: {query}")

        articles = search_naver_news(query, naver_id, naver_secret)
        if not articles:
            print(f"[INFO]   결과 없음 또는 검색 실패. 다음 기자로 진행.")
            continue

        for article in articles:
            url = pick_url(article)
            if not url:
                continue

            aid = article_id(url)
            if aid in seen_ids:
                total_skipped += 1
                continue

            if not passes_filters(article, reporter):
                total_filtered += 1
                continue

            message = format_message(article, reporter)
            ok = send_telegram(message, bot_token, chat_id)
            if not ok:
                continue

            seen_ids.add(aid)
            sent_data["sent"].append({
                "id": aid,
                "reporter": reporter["name"],
                "press": reporter.get("press", ""),
                "title": article["title"],
                "url": url,
                "published_at": article.get("pubDate", ""),
                "sent_at": datetime.now(KST).isoformat(),
            })
            total_sent += 1
            time.sleep(TELEGRAM_RATE_LIMIT_SLEEP)

    save_sent(sent_data)

    print(
        f"[INFO] === 완료 — 전송: {total_sent}건, "
        f"중복 스킵: {total_skipped}건, "
        f"필터 제외: {total_filtered}건 ==="
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
