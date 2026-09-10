"""현재 수집기가 공통으로 사용하는 HTTP·정규화 도우미.

이 파일은 온라인 실행 환경에서 `collect_source_material_v2_1.py`가
독립적으로 동작하도록 유지하는 최소 호환 모듈이다.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime, timedelta, timezone


KST = timezone(timedelta(hours=9))


def get_json(url: str) -> dict:
    """GET 요청의 JSON 응답을 반환한다."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "news-item-radar/2.3"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _integer(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def video_record(item: dict, lenses: set[str], now: datetime) -> dict:
    """YouTube videos.list 항목을 누적 장부의 공통 형식으로 바꾼다."""
    snippet = item.get("snippet", {})
    statistics = item.get("statistics", {})
    video_id = item.get("id", "")
    published_at = snippet.get("publishedAt", "")

    try:
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        age_hours = max(
            (now.astimezone(timezone.utc) - published.astimezone(timezone.utc)).total_seconds() / 3600,
            1.0,
        )
    except (TypeError, ValueError):
        age_hours = 1.0

    views = _integer(statistics.get("viewCount"))
    return {
        "id": video_id,
        "title": snippet.get("title", ""),
        "channel": snippet.get("channelTitle", ""),
        "description": snippet.get("description", ""),
        "published_at": published_at,
        "views": views,
        "views_per_hour": round(views / age_hours, 1),
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "lenses": sorted(lenses),
    }


def _average(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def collect_naver(
    config: dict,
    client_id: str,
    client_secret: str,
    today: date,
) -> list[dict]:
    """네이버 검색어 트렌드의 최근 7일과 직전 7일을 비교한다."""
    start_day = today - timedelta(days=13)
    lenses = config.get("lenses", [])
    keyword_groups = [
        {
            "groupName": lens["name"],
            "keywords": lens.get("search_terms", [])[:20],
        }
        for lens in lenses[:5]
        if lens.get("name") and lens.get("search_terms")
    ]
    if not keyword_groups:
        return []

    payload = {
        "startDate": start_day.isoformat(),
        "endDate": today.isoformat(),
        "timeUnit": "date",
        "keywordGroups": keyword_groups,
    }
    request = urllib.request.Request(
        "https://openapi.naver.com/v1/datalab/search",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
            "Content-Type": "application/json",
            "User-Agent": "news-item-radar/2.3",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))

    by_title = {row.get("title"): row for row in result.get("results", [])}
    output = []
    for lens in lenses[:5]:
        trend = by_title.get(lens.get("name"), {})
        values_by_day = {
            row.get("period"): float(row.get("ratio", 0) or 0)
            for row in trend.get("data", [])
        }
        values = [
            values_by_day.get((start_day + timedelta(days=offset)).isoformat(), 0.0)
            for offset in range(14)
        ]
        previous = _average(values[:7])
        recent = _average(values[7:])
        output.append(
            {
                "lens": lens.get("name", ""),
                "question": lens.get("question", ""),
                "search_terms": lens.get("search_terms", []),
                "recent_7d": recent,
                "previous_7d": previous,
                "ratio": round(recent / previous, 2) if previous > 0 else None,
            }
        )
    return output
