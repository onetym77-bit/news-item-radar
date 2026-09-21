#!/usr/bin/env python3
"""Validate the editorial candidate contract without judging facts automatically."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "app-ui-v1" / "data" / "latest.json"
GENERIC = ("이 사안이 서울 시민에게 어떤 영향을 주는가?", "공식 자료와 현장 확인 전의 탐색 단서")
REQUIRED = ("title", "seed_event", "structural_question", "citizen_questions", "reporting_paths", "evidence")

def main() -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    brief = data.get("editorialBrief", {})
    candidates = brief.get("candidates", [])
    errors = []
    if brief.get("input") == "editorial-v2/output/briefing_latest.json":
        errors.append("stale_editorial_brief_fallback")
    seen_topics = set()
    for index, item in enumerate(candidates, 1):
        missing = [field for field in REQUIRED if not item.get(field)]
        if missing:
            errors.append(f"candidate_{index}_missing:{','.join(missing)}")
        if item.get("topic") in seen_topics:
            errors.append(f"candidate_{index}_duplicate_topic")
        seen_topics.add(item.get("topic"))
        text = json.dumps(item, ensure_ascii=False)
        for phrase in GENERIC:
            if phrase in text:
                errors.append(f"candidate_{index}_generic_phrase")
                break
    if len(candidates) > 3:
        errors.append("more_than_three_candidates")
    print(json.dumps({"candidate_count": len(candidates), "errors": errors}, ensure_ascii=False))
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
