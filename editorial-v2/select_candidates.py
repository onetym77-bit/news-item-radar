#!/usr/bin/env python3
"""Select new editorial candidates from raw source feed, not prior review cards."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "source-scout-v1" / "output" / "daily_feed_latest.json"
OUT_DIR = ROOT / "editorial-v2" / "output"
JSON_OUT = OUT_DIR / "briefing_latest.json"
MD_OUT = OUT_DIR / "briefing_latest.md"

# Known items already reviewed or explicitly selected by the editor.
EXCLUDED_MARKERS = (
    "버스 통상임금", "시내버스 통상임금", "수어통역", "수어통역센터",
    "전세사기", "국회대로", "상부공원화", "위기 여성 청소년",
    "청소년 쉼터", "안심ON센터",
)
SOURCE_EXCLUDED = ("건설알림이", "건설 알림이", "공사 변화 관측")
HARM_TERMS = ("피해", "부담", "공백", "폐쇄", "내몰", "지연", "격차", "대기", "안전", "비용")


def clean(value: object) -> str:
    return " ".join(str(value or "").split())


def load_feed() -> dict:
    try:
        return json.loads(FEED.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def title_for(row: dict) -> str:
    subject = clean(row.get("context_subject"))
    if subject and not any(marker in subject for marker in ("문맥", "확인 필요")):
        return subject
    text = clean(row.get("text") or row.get("context_text"))
    return text[:72].rstrip() + ("…" if len(text) > 72 else "")


def question_for(row: dict) -> str:
    question = clean(row.get("question"))
    if question and "문맥 잠금 미완료" not in question and "질문 생성 전" not in question:
        return question
    subject = title_for(row)
    return (
        f"{subject}이 실제로 서울 시민에게 어떤 영향과 부담을 만들었는지, "
        "발언의 수치·기준기간·대상·책임 주체를 원자료로 확인할 수 있는가?"
    )


def score(row: dict) -> int:
    text = " ".join(clean(row.get(k)) for k in ("context_subject", "context_text", "text", "context_reason"))
    points = 0
    if clean(row.get("url")):
        points += 3
    if clean(row.get("source_name")):
        points += 2
    if clean(row.get("affected_group")):
        points += 2
    if clean(row.get("speaker")):
        points += 1
    points += min(sum(term in text for term in HARM_TERMS), 3)
    return points


def eligible(row: dict) -> bool:
    source = clean(row.get("source_name"))
    text = " ".join(clean(row.get(k)) for k in ("context_subject", "context_text", "text"))
    if not clean(row.get("url")) or not text:
        return False
    if any(term in source for term in SOURCE_EXCLUDED):
        return False
    if any(marker in text for marker in EXCLUDED_MARKERS):
        return False
    return True


def make_candidate(row: dict) -> dict:
    subject = title_for(row)
    source = clean(row.get("source_name")) or "공식 원자료"
    question = question_for(row)
    return {
        "candidate_id": clean(row.get("candidate_id")) or clean(row.get("source_revision")),
        "title": subject,
        "topic": subject,
        "selection_reason": (
            f"{source}의 원자료 피드에서 새로 확인된 단서입니다. "
            "기존 검토·선정 항목은 제외했으며, 시민 영향과 책임 주체를 독립 확인할 수 있을 때 "
            "6~7분 기획 리포트로 확장할 수 있습니다."
        ),
        "citizen_question": question,
        "uncommon_angle": (
            "발언이나 발표를 사실로 확정하지 않고, 실제 대상·규모·기간·책임 주체와 "
            "대체수단의 존재 여부를 확인합니다."
        ),
        "evidence": [{
            "source": source,
            "date": clean(row.get("source_date") or row.get("speech_date")),
            "url": clean(row.get("url")),
        }],
        "needs_verification": [
            "수치·기준기간·대상 범위 원문 대조",
            "현재 진행 여부와 실제 시민 영향 확인",
            "기존 보도와 다른 취재 각도 확인",
        ],
        "source": source,
        "status": "새 원자료 검토",
        "score": score(row),
    }


def main() -> int:
    feed = load_feed()
    raw = list(feed.get("editorial_triage", [])) + list(feed.get("context_holds", []))
    selected = []
    seen = set()
    for row in sorted(raw, key=score, reverse=True):
        if not eligible(row):
            continue
        item = make_candidate(row)
        key = item["title"]
        if key in seen:
            continue
        seen.add(key)
        selected.append(item)
        if len(selected) >= 3:
            break

    now = datetime.now(timezone(timedelta(hours=9))).isoformat()
    payload = {
        "schema": 2,
        "generated_at_kst": now,
        "run_policy": "월·수 09:00 KST, 원자료 피드에서 최대 3건",
        "input": "source-scout-v1/output/daily_feed_latest.json",
        "count": len(selected),
        "candidates": selected,
        "quality_gate": {
            "existing_items_excluded": list(EXCLUDED_MARKERS),
            "primary_source_excluded": list(SOURCE_EXCLUDED),
            "empty_result_is_valid": True,
            "human_review_required": True,
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = ["# 서울 기획 아이템 브리핑 v2", "", f"- 생성 시각: {now}", "- 입력: 원자료 피드", f"- 새 후보: {len(selected)}건", ""]
    for i, item in enumerate(selected, 1):
        ev = item["evidence"][0]
        lines.extend([
            f"## {i}. {item['title']}",
            "",
            f"- 주제: {item['topic']}",
            f"- 선정 이유: {item['selection_reason']}",
            f"- 시민 질문: {item['citizen_question']}",
            f"- 다른 각도: {item['uncommon_angle']}",
            f"- 근거: {ev['source']} ({ev['date'] or '날짜 미상'})",
            f"- 원문: {ev['url']}",
            "- 상태: 사람 검토 필요",
            "- 확인 필요: 수치·기준기간·대상·현재성·차별화 각도",
            "",
        ])
    if not selected:
        lines.append("현재 기존 항목을 제외하고 기준을 충족한 새 후보가 없습니다.")
    MD_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"selected={len(selected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
