#!/usr/bin/env python3
"""Turn discovery signals into structural editorial questions for human review."""
from __future__ import annotations
import json, re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "interest-signal-pilot" / "output" / "interest_signals_latest.json"
OUTPUT = ROOT / "interest-signal-pilot" / "output" / "review_queue_latest.json"

def published_key(row: dict) -> float:
    try:
        value = parsedate_to_datetime(row.get("published_at", "")).timestamp()
        return value
    except (TypeError, ValueError, OverflowError):
        return 0.0

def story_key(title: str) -> str:
    value = re.sub(r"[^0-9a-z가-힣]+", " ", title.lower())
    return re.sub(r"\s+", " ", value).strip()[:100]

def make_item(row: dict) -> dict:
    title = row.get("title", "").strip()
    topic = row.get("query", "서울 지역 현안")
    return {
        "review_id": row.get("url", "").split("/")[-1][:24] or title[:24],
        "seed_event": title,
        "topic": topic,
        "structural_question": f"이 사건은 서울에서 {topic} 문제가 특정 지역과 시민에게 집중되는 구조를 보여주는가?",
        "scope_hypothesis": "한 지역의 사례가 서울 다른 자치구에서도 반복되는지 비교한다.",
        "reason": "지역 뉴스 관심 신호에서 출발해 서울 전체의 제도·배치·책임 구조로 확장할 수 있는지 검토하기 위해",
        "conflict_groups": ["직접 affected 시민·이용자", "인근 주민", "서울시·자치구", "사업자·기관"],
        "citizen_questions": [
            "이 사안의 부담과 혜택은 누구에게 돌아가는가?",
            "같은 문제가 서울 다른 지역에서도 반복되는가?",
            "공공이 설명·지원·대체수단을 제공했는가?",
        ],
        "reporting_paths": [
            "서울시·자치구 공식 계획·예산·통계 확인",
            "25개 자치구 유사 사례 비교",
            "당사자·주민·책임 기관 인터뷰",
        ],
        "title_options": [
            f"서울 곳곳 ‘{topic}’…문제는 왜 특정 지역에 몰리나",
            f"한 지역 사건에서 서울 전체의 ‘{topic}’을 묻다",
        ],
        "evidence": [{"type": "news", "url": row.get("url"), "published_at": row.get("published_at")}],
        "status": "DISCOVERY_ONLY",
        "editorial_status": "확장 질문 초안",
        "needs_human_review": True,
        "needs_official_cross_check": True,
        "source_query": topic,
    }

def main() -> int:
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    rows = sorted(payload.get("news_signals", []), key=published_key, reverse=True)
    # Keep discovery breadth: interleave query groups instead of taking 30 from one topic.
    grouped = {}
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
        "schema": 2,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_snapshot": payload.get("generated_at_utc"),
        "candidate_ready": False,
        "review_count": len(queue),
        "items": queue,
        "policy": "관심 신호는 자동 후보가 아니며, 출발 사건에서 구조적 질문을 확장한 뒤 공식 자료·시민 영향 확인을 거쳐 사람이 판정한다.",
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"review_queue={len(queue)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
