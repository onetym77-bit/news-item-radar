#!/usr/bin/env python3
"""Turn discovery signals into a human-review queue without auto-promoting candidates."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "interest-signal-pilot" / "output" / "interest_signals_latest.json"
OUTPUT = ROOT / "interest-signal-pilot" / "output" / "review_queue_latest.json"


def main() -> int:
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    rows = payload.get("news_signals", [])
    rows.sort(key=lambda row: row.get("published_at", ""), reverse=True)
    queue = []
    for row in rows[:30]:
        queue.append({
            "review_id": row.get("url", "").split("/")[-1][:24] or row.get("title", "")[:24],
            "title": row.get("title", ""),
            "topic": row.get("query", ""),
            "reason": "검색·뉴스 관심 신호에서 발견된 지역 이슈",
            "citizen_question": "이 사안이 서울 시민의 생활·비용·안전에 어떤 영향을 주는가?",
            "uncommon_angle": "공식 자료와 현장 확인 전의 탐색 단서",
            "evidence": [{"type": "news", "url": row.get("url"), "published_at": row.get("published_at")}],
            "status": "DISCOVERY_ONLY",
            "needs_human_review": True,
            "needs_official_cross_check": True,
            "source_query": row.get("query"),
        })
    output = {
        "schema": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_snapshot": payload.get("generated_at_utc"),
        "candidate_ready": False,
        "review_count": len(queue),
        "items": queue,
        "policy": "관심 신호는 자동 후보가 아니며, 공식 자료·시민 영향 확인 뒤 사람이 판정한다.",
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"review_queue={len(queue)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
