#!/usr/bin/env python3
"""Keep news search results as signals until their source context is reviewed."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "interest-signal-pilot" / "output" / "interest_signals_latest.json"
OUTPUT = ROOT / "interest-signal-pilot" / "output" / "review_queue_latest.json"


def published_key(row: dict) -> float:
    try:
        return parsedate_to_datetime(row.get("published_at", "")).timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0.0


def story_key(title: str) -> str:
    value = re.sub(r"[^0-9a-z가-힣]+", " ", title.lower())
    return re.sub(r"\s+", " ", value).strip()[:100]


def make_item(row: dict) -> dict:
    title = row.get("title", "").strip()
    headline = re.split(r"\s[-|]\s", title, maxsplit=1)[0].strip()
    return {
        "review_id": row.get("url", "").split("/")[-1][:24] or story_key(title)[:24],
        "headline": headline,
        "source_headline": title,
        "source_query": row.get("query", ""),
        "source_name": "검색 관심도·뉴스 확산",
        "observed_signal": "뉴스 검색 결과에서 이 기사 제목과 게시일을 확인했습니다.",
        "source_context_status": "TITLE_ONLY",
        "problem_status": "UNASSESSED",
        "first_check": "기사 본문을 읽고 실제 사건·시민 경험인지, 발표·예방 안내인지 구분",
        "counterpossibility": "제목만으로는 시민의 피해나 제도 공백이 확인되지 않음",
        "promotion_status": "HOLD",
        "status": "DISCOVERY_ONLY",
        "needs_human_review": True,
        "screening_hint": row.get("editorial_reason", ""),
        "screening_priority": "높음" if row.get("editorial_eligible") else "보통",
        "evidence": [{
            "type": "news_search_result",
            "url": row.get("url", ""),
            "published_at": row.get("published_at", ""),
        }],
    }


def main() -> int:
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    rows = sorted(payload.get("news_signals", []), key=published_key, reverse=True)
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row.get("query", "기타"), []).append(row)

    unique, seen = [], set()
    while grouped and len(unique) < 30:
        for query in list(grouped):
            row = grouped[query].pop(0)
            key = story_key(row.get("title", ""))
            if key and key not in seen:
                seen.add(key)
                unique.append(row)
            if not grouped[query]:
                del grouped[query]
            if len(unique) >= 30:
                break

    queue = [make_item(row) for row in unique]
    output = {
        "schema": 4,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_snapshot": payload.get("generated_at_utc"),
        "candidate_ready": False,
        "review_count": len(queue),
        "items": queue,
        "policy": "제목 검색은 발견 신호다. 본문 맥락과 시민에게 의미 있는 구체적 질문을 확인하기 전에는 기획 후보로 승격하지 않는다. 신규 사업은 피해 통계가 없어도 질문 가치로 검토한다.",
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"review_queue={len(queue)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
