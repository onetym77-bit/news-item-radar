#!/usr/bin/env python3
"""Collect public interest signals from Google News RSS searches.

This is a discovery feed only. It does not treat search volume, headlines,
or article repetition as proof of a claim.
"""
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
    "서울 민원",
    "서울 공사 지연",
    "서울 안전 사고",
    "서울 재개발 갈등",
    "서울 교통 불편",
    "서울 주거 피해",
    "서울 복지 공백",
    "서울 자치구 논란",
]
RSS_TEMPLATE = "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
USER_AGENT = "news-item-radar/interest-signal-pilot"


def clean(value: str | None) -> str:
    return " ".join((value or "").split())


def fetch(query: str) -> list[dict]:
    url = RSS_TEMPLATE.format(query=urllib.parse.quote_plus(query))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        root = ET.fromstring(response.read())
    rows = []
    for item in root.findall("./channel/item"):
        title = clean(item.findtext("title"))
        link = clean(item.findtext("link"))
        pub_date = clean(item.findtext("pubDate"))
        description = re.sub("<[^>]+>", " ", item.findtext("description") or "")
        if not title or not link:
            continue
        rows.append({
            "query": query,
            "title": title,
            "url": link,
            "published_at": pub_date,
            "summary": clean(description)[:500],
            "signal_type": "NEWS_ATTENTION",
            "status": "DISCOVERY_SIGNAL",
        })
    return rows


def main() -> int:
    collected: list[dict] = []
    errors: list[dict] = []
    for query in QUERIES:
        try:
            collected.extend(fetch(query))
        except Exception as exc:  # one failed query must not erase other signals
            errors.append({"query": query, "error": type(exc).__name__})

    unique: dict[str, dict] = {}
    for row in collected:
        unique.setdefault(row["url"], row)

    payload = {
        "schema": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_id": "search_news_interest",
        "source_name": "검색 관심도·뉴스 확산",
        "collection_mode": "google_news_rss_keyword_probe",
        "queries": QUERIES,
        "count": len(unique),
        "signals": list(unique.values())[:100],
        "errors": errors,
        "limitations": [
            "뉴스 노출과 반복 보도는 시민 전체 의견이나 사실 확정이 아님",
            "검색량·조회수 자료가 없으면 관심도는 뉴스 확산의 대리 신호로만 표시",
            "후보 승격 전 서울시의회·구의회·감사·통계·현장 확인 필요",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"signals={len(unique)} errors={len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
