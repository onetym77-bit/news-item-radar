#!/usr/bin/env python3
"""Collect and quality-gate public interest signals from Google News RSS and Naver DataLab."""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "interest-signal-pilot" / "output" / "interest_signals_latest.json"
QUERIES = [
    "서울 민원", "서울 공사 지연", "서울 안전 사고", "서울 재개발 갈등",
    "서울 교통 불편", "서울 주거 피해", "서울 복지 공백", "서울 자치구 논란",
]
SEOUL_AREAS = [
    "서울", "종로", "중구", "용산", "성동", "광진", "동대문", "중랑", "성북",
    "강북", "도봉", "노원", "은평", "서대문", "마포", "양천", "강서", "구로",
    "금천", "영등포", "동작", "관악", "서초", "강남", "송파", "강동",
]
SEOUL_NAME_ONLY = ("서울뉴스", "서울연구원", "서울본부", "서울자치신문", "서울뉴스통신")
RSS_TEMPLATE = "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
NAVER_URL = "https://openapi.naver.com/v1/datalab/search"
USER_AGENT = "news-item-radar/interest-signal-pilot"


def clean(value: str | None) -> str:
    return " ".join((value or "").split())


def title_key(value: str) -> str:
    value = value.lower()
    value = re.sub(r"\[[^]]+\]|【[^】]+】|\([^)]*\)", " ", value)
    value = re.sub(r"[^0-9a-z가-힣]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def seoul_relevance(title: str, summary: str) -> tuple[bool, str]:
    # RSS title ends with a publisher after " - ". Never use publisher text as location evidence.
    headline = re.split(r"\s[-|]\s", title, maxsplit=1)[0].strip()
    for area in SEOUL_AREAS:
        if area not in headline:
            continue
        if area == "서울" and any(name in headline for name in SEOUL_NAME_ONLY):
            continue
        return True, f"기사 제목의 지역 표현: {area}"
    return False, "기사 제목에서 서울·자치구 명칭 미확인"


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
        summary = clean(description)[:500]
        relevant, reason = seoul_relevance(title, summary)
        rows.append({
            "query": query,
            "title": title,
            "url": link,
            "published_at": clean(item.findtext("pubDate")),
            "summary": summary,
            "seoul_relevant": relevant,
            "relevance_reason": reason,
            "signal_type": "NEWS_ATTENTION",
            "status": "DISCOVERY_SIGNAL",
        })
    return rows


def fetch_naver_trends() -> tuple[list[dict], str | None, int, list[str]]:
    client_id = os.getenv("NAVER_CLIENT_ID", "").strip()
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return [], "missing_credentials", 0, []
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=14)
    body = {
        "startDate": start.isoformat(),
        "endDate": today.isoformat(),
        "timeUnit": "date",
        "keywordGroups": [{"groupName": q, "keywords": [q]} for q in QUERIES[:5]],
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
        return [], type(exc).__name__, 0, []
    rows = []
    groups_seen = 0
    groups_without_data = []
    for group in result.get("results", []):
        groups_seen += 1
        title = group.get("title", "")
        data = group.get("data", [])
        if not data:
            groups_without_data.append(title)
        for point in data:
            rows.append({
                "query": title,
                "period": point.get("period"),
                "relative_ratio": point.get("ratio"),
                "signal_type": "NAVER_SEARCH_TREND",
                "status": "DISCOVERY_SIGNAL",
            })
    return rows, None, groups_seen, groups_without_data


def main() -> int:
    raw_news: list[dict] = []
    errors: list[dict] = []
    for query in QUERIES:
        try:
            raw_news.extend(fetch_news(query))
        except Exception as exc:
            errors.append({"channel": "google_news_rss", "query": query, "error": type(exc).__name__})

    relevant_news = [row for row in raw_news if row["seoul_relevant"]]
    unique: dict[str, dict] = {}
    for row in relevant_news:
        key = title_key(row["title"])
        if key and key not in unique:
            unique[key] = row
    news = list(unique.values())

    trends, trend_error, trend_groups, trend_groups_without_data = fetch_naver_trends()
    if trend_error:
        errors.append({"channel": "naver_datalab", "error": trend_error})

    trend_summary = []
    by_query: dict[str, list[dict]] = {}
    for row in trends:
        by_query.setdefault(row["query"], []).append(row)
    for query, rows in by_query.items():
        rows = [r for r in rows if isinstance(r.get("relative_ratio"), (int, float))]
        if not rows:
            continue
        peak = max(rows, key=lambda r: r["relative_ratio"])
        latest = max(rows, key=lambda r: r.get("period") or "")
        trend_summary.append({
            "query": query,
            "peak_period": peak.get("period"),
            "peak_ratio": peak.get("relative_ratio"),
            "latest_period": latest.get("period"),
            "latest_ratio": latest.get("relative_ratio"),
            "data_points": len(rows),
        })

    payload = {
        "schema": 4,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_id": "search_news_interest",
        "source_name": "검색 관심도·뉴스 확산",
        "collection_mode": ["google_news_rss_keyword_probe", "naver_datalab_search_trend"],
        "queries": QUERIES,
        "quality_gate": {
            "raw_news_count": len(raw_news),
            "seoul_relevant_count": len(relevant_news),
            "unique_news_count": len(news),
            "duplicate_or_irrelevant_count": len(raw_news) - len(news),
            "trend_groups": trend_groups,
            "trend_groups_without_data": trend_groups_without_data,
            "trend_data_points": len(trends),
            "candidate_ready": False,
            "reason": "관심 신호는 탐색용이며, 후보 승격 전 원문·시민 영향·책임 주체 확인 필요",
        },
        "news_count": len(news),
        "trend_count": len(trends),
        "news_signals": news[:120],
        "trend_signals": trends[:500],
        "trend_summary": trend_summary,
        "errors": errors,
        "limitations": [
            "네이버 데이터랩 ratio는 절대 검색량이 아닌 상대 지수임",
            "검색·뉴스 반복은 시민 전체 의견이나 사실 확정이 아님",
            "동일·유사 제목은 묶었지만 기사 내용의 사실성은 검증하지 않음",
            "지역성은 기사 제목 기준의 1차 분류이며 최종 사실 확인이 아님",
            "후보 승격 전 서울시의회·구의회·감사·통계·현장 확인 필요",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"raw_news={len(raw_news)} relevant={len(relevant_news)} "
        f"unique={len(news)} trends={len(trends)} errors={len(errors)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
