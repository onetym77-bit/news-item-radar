#!/usr/bin/env python3
"""Reject accidental promotion of title-only signals into editorial candidates."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "app-ui-v1" / "data" / "latest.json"
GENERIC = ("이 사안이 서울 시민에게 어떤 영향을 주는가?", "공식 자료와 현장 확인 전의 탐색 단서")
CANDIDATE_REQUIRED = (
    "title", "seed_event", "editorial_question", "citizen_relevance",
    "counterpossibility", "first_check", "promotion_basis", "evidence",
)


def main() -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    brief = data.get("editorialBrief", {})
    candidates = brief.get("candidates", [])
    signals = brief.get("discovery_signals")
    errors = []

    if brief.get("input") == "editorial-v2/output/briefing_latest.json":
        errors.append("stale_editorial_brief_fallback")
    if not isinstance(signals, list):
        errors.append("discovery_signals_missing")
        signals = []

    seen_ids = set()
    for index, item in enumerate(signals, 1):
        signal_id = item.get("review_id")
        if not signal_id or signal_id in seen_ids:
            errors.append(f"signal_{index}_missing_or_duplicate_id")
        seen_ids.add(signal_id)
        if not item.get("headline") or not item.get("evidence"):
            errors.append(f"signal_{index}_missing_source_anchor")
        context = item.get("source_context_status")
        if context not in {"TITLE_ONLY", "BODY_UNAVAILABLE", "BODY_READ"}:
            errors.append(f"signal_{index}_context_mislabeled")
        if context == "BODY_READ" and not any(e.get("type") == "publisher_article" for e in item.get("evidence", [])):
            errors.append(f"signal_{index}_missing_publisher_anchor")
        if context != "BODY_READ" and item.get("editorial_question"):
            errors.append(f"signal_{index}_question_without_body")
        if item.get("problem_status") != "UNASSESSED":
            errors.append(f"signal_{index}_problem_assumed")
        if item.get("structural_question") or item.get("title_options"):
            errors.append(f"signal_{index}_unreviewed_story_angle")

    for index, item in enumerate(candidates, 1):
        missing = [field for field in CANDIDATE_REQUIRED if not item.get(field)]
        if missing:
            errors.append(f"candidate_{index}_missing:{','.join(missing)}")
        if item.get("promotion_status") != "APPROVED":
            errors.append(f"candidate_{index}_unapproved")
        if item.get("source_context_status") == "TITLE_ONLY":
            errors.append(f"candidate_{index}_title_only")
        if item.get("status") == "DISCOVERY_ONLY":
            errors.append(f"candidate_{index}_discovery_status")
        text = json.dumps(item, ensure_ascii=False)
        if any(phrase in text for phrase in GENERIC):
            errors.append(f"candidate_{index}_generic_phrase")

    if len(signals) > 3:
        errors.append("more_than_three_discovery_signals")
    if len(candidates) > 3:
        errors.append("more_than_three_candidates")
    if brief.get("count") != len(candidates):
        errors.append("candidate_count_mismatch")

    print(json.dumps({
        "candidate_count": len(candidates),
        "discovery_count": len(signals),
        "errors": errors,
    }, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
