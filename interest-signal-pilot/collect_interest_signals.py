#!/usr/bin/env python3
"""Collect public interest signals from Google News RSS and Naver DataLab."""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "interest-signal-pilot" / "output" / "interest_signals_latest.json"
QUERIES = [
    "서울 민원", "서울 공사 지연", "서울 안전 사고", "서울 재개발 갈등",
    "서울 교통 불편", "서울 주거 피해", "서울 복지 공백", "서울 자치구 논란",
]
RSS_TEMPLATE = "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
NAVER_URL = "https://openapi.naver.com/v1/datalab/search"
USER_AGENT = "news-item-radar/interest-signal-pilot"


def clean(value: str | None) -> str:
    return " ".join((value or "").split())


def fetch_news(query: str) -> list[dict]:
    url = RSS_TEMPLATE.format(query=urllib.parse.quote_plus(query))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        root = ET.fromstring(response.read())
    rows = []
    for item in root.findall("./channel/item"):
        title = clean(item.findtext("title"))
        link = clean(item.findtext("link"))
        if not title or not link:
            continue
        description = re.sub("<[^>]+>", " ", item.findtext("description") or "")
        rows.append({
            "query": query, "title": title, "url": link,
            "published_at": clean(item.findtext("pubDate")),
            "summary": clean(description)[:500],
            "signal_type": "NEWS_ATTENTION", "status": "DISCOVERY_SIGNAL",
        })
    return rows


def fetch_naver_trends() -> tuple[list[dict], str | None]:
    client_id = os.getenv("NAVER_CLIENT_ID", "").strip()
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return [], "missing_credentials"
    today = datetime.now(timezone.utc).date()
    start = today.replace(day=max(1, today.day - 14))
    body = {
        "startDate": start.isoformat(),
        "endDate": today.isoformat(),
        "timeUnit": "date",
        "keywordGroups": [
            {"groupName": q, "keywords": [q]} for q in QUERIES[:5]
        ],
    }
    request = urllib.request.Request(
        NAVER_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return [], type(exc).__name__
    rows = []
    for group in result.get("results", []):
        for point in group.get("data", []):
            rows.append({
                "query": group.get("title", ""),
                "period": point.get("period"),
                "relative_ratio": point.get("ratio"),
                "signal_type": "NAVER_SEARCH_TREND",
                "status": "DISCOVERY_SIGNAL",
            })
    return rows, None


def main() -> int:
    news: list[dict] = []
    errors: list[dict] = []
    for query in QUERIES:
        try:
            news.extend(fetch_news(query))
        except Exception as exc:
            errors.append({"channel": "google_news_rss", "query": query, "error": type(exc).__name__})
    trends, trend_error = fetch_naver_trends()
    if trend_error:
        errors.append({"channel": "naver_datalab", "error": trend_error})
    unique = {}
    for row in news:
        unique.setdefault(row["url"], row)
    payload = {
        "schema": 2,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_id": "search_news_interest",
        "source_name": "검색 관심도·뉴스 확산",
        "collection_mode": ["google_news_rss_keyword_probe", "naver_datalab_search_trend"],
        "queries": QUERIES,
        "news_count": len(unique),
        "trend_count": len(trends),
        "news_signals": list(unique.values())[:100],
        "trend_signals": trends[:500],
        "errors": errors,
        "limitations": [
            "네이버 데이터랩 ratio는 절대 검색량이 아닌 상대 지수임",
            "검색·뉴스 반복은 시민 전체 의견이나 사실 확정이 아님",
            "후보 승격 전 서울시의회·구의회·감사·통계·현장 확인 필요",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"news={len(unique)} trends={len(trends)} errors={len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
