#!/usr/bin/env python3
"""Select 2-3 citizen-facing editorial candidates from existing source outputs.

This is intentionally deterministic and conservative. It does not promote
observations or rows without a title, question, and source URL.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "source-scout-v1" / "output" / "editorial_review_cards_latest.json"
OUT_DIR = ROOT / "editorial-v2" / "output"
JSON_OUT = OUT_DIR / "briefing_latest.json"
MD_OUT = OUT_DIR / "briefing_latest.md"

EXCLUDED_SOURCE_TERMS = ("건설알림이", "건설 알림이", "공사 변화 관측")
PREFERRED_SOURCE_TERMS = ("의회", "감사", "뉴스", "민원", "시민제안", "SNS", "유튜브")


def read_cards() -> list[dict]:
    try:
        data = json.loads(INPUT.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    return data.get("review_cards", [])


def clean(value: object) -> str:
    return str(value or "").strip()


def score(card: dict) -> int:
    source = clean(card.get("source_name"))
    subject = clean(card.get("context_subject"))
    question = clean(card.get("question") or card.get("fact"))
    url = clean(card.get("url"))
    points = 0
    if subject:
        points += 3
    if question:
        points += 3
    if url:
        points += 2
    if any(term in source for term in PREFERRED_SOURCE_TERMS):
        points += 2
    if len(question) >= 45:
        points += 1
    if any(term in f"{subject} {question}" for term in ("지원", "피해", "지연", "공백", "격차", "비용", "안전")):
        points += 1
    return points


def candidate(card: dict) -> dict | None:
    subject = clean(card.get("context_subject"))
    source = clean(card.get("source_name"))
    question = clean(card.get("question") or card.get("fact"))
    url = clean(card.get("url"))
    if not subject or not source or not question or not url:
        return None
    if any(term in source for term in EXCLUDED_SOURCE_TERMS):
        return None
    return {
        "candidate_id": clean(card.get("candidate_id")),
        "title": subject,
        "topic": subject,
        "selection_reason": (
            f"{source}에서 확인된 사안으로, 시민 생활·권리·공공서비스에 미치는 "
            "영향을 추가 확인할 수 있고 6~7분 기획 리포트로 확장할 질문이 있습니다."
        ),
        "citizen_question": question,
        "uncommon_angle": (
            "발언이나 발표 내용을 사실로 확정하지 않고, 실제 대상·규모·기간·책임 주체가 "
            "시민에게 어떤 차이를 만드는지 확인합니다."
        ),
        "evidence": [{"source": source, "date": clean(card.get("source_date") or card.get("speech_date")), "url": url}],
        "needs_verification": [
            "수치·기간·대상 범위를 원문과 관련 자료로 재확인",
            "현재 진행 여부와 시민 영향 확인",
            "기존 보도와 다른 취재 각도 확인",
        ],
        "source": source,
        "score": score(card),
    }


def main() -> int:
    selected = []
    seen = set()
    for raw in sorted(read_cards(), key=score, reverse=True):
        item = candidate(raw)
        if not item or item["title"] in seen:
            continue
        seen.add(item["title"])
        selected.append(item)
        if len(selected) == 3:
            break

    now = datetime.now(timezone(timedelta(hours=9))).isoformat()
    payload = {
        "schema": 1,
        "generated_at_kst": now,
        "run_policy": "월·수 09:00 KST, 최대 3건",
        "count": len(selected),
        "candidates": selected,
        "quality_gate": {
            "required_fields": ["title", "topic", "selection_reason", "citizen_question", "uncommon_angle", "evidence"],
            "excluded_as_primary": ["건설알림이 변화 관측"],
            "empty_result_is_valid": True,
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = ["# 서울 기획 아이템 브리핑 v2", "", f"- 생성 시각: {now}", f"- 후보: {len(selected)}건", ""]
    for index, item in enumerate(selected, 1):
        lines.extend([
            f"## {index}. {item['title']}",
            "",
            f"- 주제: {item['topic']}",
            f"- 선정 이유: {item['selection_reason']}",
            f"- 시민 질문: {item['citizen_question']}",
            f"- 다른 각도: {item['uncommon_angle']}",
            f"- 근거: {item['evidence'][0]['source']} ({item['evidence'][0]['date'] or '날짜 미상'})",
            f"- 원문: {item['evidence'][0]['url']}",
            "- 확인 필요: 수치·기간·대상·현재성·차별화 각도",
            "",
        ])
    if not selected:
        lines.append("현재 기준을 충족한 후보가 없습니다. 빈 결과를 정상 상태로 기록합니다.")
    MD_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"selected={len(selected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
