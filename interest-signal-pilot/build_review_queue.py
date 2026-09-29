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
SEEN = ROOT / "interest-signal-pilot" / "output" / "seen_news.json"


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
        "title_key": row.get("title_key") or story_key(title),
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
        "discovery_lane": row.get("signal_lane") or "CITIZEN_ATTENTION",
        "is_new": row.get("is_new") is True,
        "screening_priority": "높음" if row.get("editorial_eligible") or row.get("signal_lane") == "WATCHDOG_DUTY" else "보통",
        "evidence": [{
            "type": "news_search_result",
            "url": row.get("url", ""),
            "published_at": row.get("published_at", ""),
        }],
    }


def main() -> int:
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    rows = [
        row for row in payload.get("news_signals", [])
        if row.get("is_new") is True
    ]
    rows = sorted(
        rows,
        key=lambda row: (bool(row.get("editorial_eligible")), published_key(row)),
        reverse=True,
    )

    def take_lane(lane: str, limit: int, seen: set[str]) -> list[dict]:
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            if (row.get("signal_lane") or "CITIZEN_ATTENTION") != lane:
                continue
            grouped.setdefault(row.get("query", "기타"), []).append(row)
        chosen = []
        while grouped and len(chosen) < limit:
            for query in list(grouped):
                row = grouped[query].pop(0)
                candidate_key = story_key(row.get("title", ""))
                if candidate_key and candidate_key not in seen:
                    seen.add(candidate_key)
                    chosen.append(row)
                if not grouped[query]:
                    del grouped[query]
                if len(chosen) >= limit:
                    break
        return chosen

    seen: set[str] = set()
    unique = take_lane("WATCHDOG_DUTY", 15, seen)
    unique.extend(take_lane("CITIZEN_ATTENTION", 15, seen))
    if len(unique) < 30:
        leftovers = sorted(rows, key=published_key, reverse=True)
        for row in leftovers:
            candidate_key = story_key(row.get("title", ""))
            if candidate_key and candidate_key not in seen:
                seen.add(candidate_key)
                unique.append(row)
            if len(unique) >= 30:
                break

    queue = [make_item(row) for row in unique]
    output = {
        "schema": 4,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_snapshot": payload.get("generated_at_utc"),
        "candidate_ready": False,
        "review_count": len(queue),
        "new_input_count": len(rows),
        "seen_input_excluded": int(payload.get("quality_gate", {}).get("seen_news_count") or 0),
        "items": queue,
        "lane_counts": {
            "공익 감시": sum(item.get("discovery_lane") == "WATCHDOG_DUTY" for item in queue),
            "시민 관심": sum(item.get("discovery_lane") != "WATCHDOG_DUTY" for item in queue),
        },
        "policy": "이번 수집 회차에 처음 발견된 제목만 검토한다. 시민 관심 경로와 관심도와 무관한 공익 감시 경로를 분리하며, 본문 맥락과 구체적 취재 가설을 확인하기 전에는 최종 후보로 승격하지 않는다.",
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        ledger = json.loads(SEEN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ledger = {}
    existing = {
        story_key(item.get("title_key") or item.get("title", "")): item
        for item in ledger.get("items", [])
        if story_key(item.get("title_key") or item.get("title", ""))
    } if ledger.get("schema") == 2 else {}
    for item in queue:
        normalized = story_key(item.get("title_key") or item.get("source_headline", ""))
        if normalized:
            existing[normalized] = {
                "title_key": normalized,
                "title": item.get("source_headline", "")[:240],
                "queued_at_utc": output["generated_at_utc"],
            }
    seen_output = {
        "schema": 2,
        "updated_at_utc": output["generated_at_utc"],
        "policy": "실제 검토 큐에 들어간 기사만 소진 처리한다.",
        "items": list(existing.values())[-2000:],
    }
    SEEN.write_text(json.dumps(seen_output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"review_queue={len(queue)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
