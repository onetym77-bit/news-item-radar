#!/usr/bin/env python3
"""Build reviewable editorial leads from the raw source feed."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "source-scout-v1" / "output" / "daily_feed_latest.json"
OUT_DIR = ROOT / "editorial-v2" / "output"
JSON_OUT = OUT_DIR / "briefing_latest.json"
MD_OUT = OUT_DIR / "briefing_latest.md"

EXCLUDED_MARKERS = (
    "버스 통상임금", "시내버스 통상임금", "수어통역", "수어통역센터",
    "전세사기", "국회대로", "상부공원화", "위기 여성 청소년",
    "청소년 쉼터", "안심ON센터",
)
SOURCE_EXCLUDED = ("건설알림이", "건설 알림이", "공사 변화 관측")


def clean(value: object) -> str:
    return " ".join(str(value or "").split())


def load_feed() -> dict:
    try:
        return json.loads(FEED.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def theme(row: dict) -> str:
    text = " ".join(clean(row.get(k)) for k in ("context_subject", "context_text", "text", "context_trigger"))
    if "AI" in text or "인공지능" in text:
        return "ai"
    if "통학" in text or "셔틀" in text:
        return "school_transport"
    if "장애인" in text or "일자리" in text:
        return "disability_work"
    if "청년" in text:
        return "youth"
    if "주거" in text or "임대" in text:
        return "housing"
    return "general"


def editorial_title(row: dict) -> str:
    t = theme(row)
    return {
        "ai": "서울 청년 AI 지원사업, 접근 격차를 줄일 수 있나",
        "school_transport": "서울 학생 통학 공백, 사설 셔틀 비용으로 전가되나",
        "disability_work": "장애인 일자리 지원, 지속 가능한 일자리로 이어지나",
        "youth": "서울 청년 지원정책, 실제 이용 장벽은 무엇인가",
        "housing": "서울 주거 지원, 필요한 시민에게 실제로 닿고 있나",
    }.get(t, clean(row.get("context_subject")) or "서울 시민 생활과 관련된 정책·서비스 문제")


def editorial_question(row: dict) -> str:
    t = theme(row)
    return {
        "ai": "서울시 청년 AI 지원사업은 누구의 어떤 장벽을 해결하려는가? 지원 규모와 방식은 실제 수요를 반영하며, 사업 효과를 확인할 기준이 있는가?",
        "school_transport": "공공 통학 지원의 공백이 사설 셔틀 비용으로 학부모에게 전가되고 있는가? 학교·자치구·서울시의 역할은 어디까지인가?",
        "disability_work": "장애인 일자리 사업이 일회성 참여에 그치지 않고 지속 가능한 고용으로 이어지는가? 참여자와 기관이 겪는 실제 제약은 무엇인가?",
        "youth": "정책의 대상과 지원 방식이 실제 이용자의 필요와 맞는가? 신청하지 못하거나 중도 이탈하는 시민은 누구인가?",
        "housing": "정책이 해결하려는 시민의 부담은 무엇이며, 지원에서 빠지는 사람은 누구인가?",
    }.get(t, "제기된 문제는 실제 이용자에게 어떻게 나타나며, 책임 주체가 제시한 대안은 작동하는가?")


def uncommon_angle(row: dict) -> str:
    t = theme(row)
    return {
        "ai": "지원액이나 참여자 수가 아니라, 무료·유료 이용 격차와 사업 효과를 측정할 기준이 있는지 확인한다.",
        "school_transport": "셔틀버스의 존재보다 공공 통학 체계의 공백과 비용 부담이 어느 가정에 집중되는지 비교한다.",
        "disability_work": "일자리 숫자가 아니라 고용 지속기간·임금·업무의 질과 당사자 선택권을 확인한다.",
        "youth": "정책 홍보가 아니라 실제 신청·접근·중도 이탈 과정에서 발생하는 장벽을 확인한다.",
        "housing": "지원 대상 숫자가 아니라 지원에서 빠진 시민의 선택과 부담을 비교한다.",
    }.get(t, "발언의 사실 여부뿐 아니라 실제 대상·규모·책임 주체와 대체수단의 존재 여부를 확인한다.")


def score(row: dict) -> int:
    text = " ".join(clean(row.get(k)) for k in ("context_subject", "context_text", "text", "context_reason"))
    return (
        (3 if clean(row.get("url")) else 0)
        + (2 if clean(row.get("source_name")) else 0)
        + (2 if clean(row.get("affected_group")) else 0)
        + (1 if clean(row.get("speaker")) else 0)
        + min(sum(term in text for term in ("피해", "부담", "공백", "폐쇄", "내몰", "지연", "격차", "비용")), 3)
    )


def eligible(row: dict) -> bool:
    source = clean(row.get("source_name"))
    text = " ".join(clean(row.get(k)) for k in ("context_subject", "context_text", "text"))
    return bool(clean(row.get("url")) and text and not any(x in source for x in SOURCE_EXCLUDED)
        and not any(x in text for x in EXCLUDED_MARKERS))


def make_candidate(row: dict) -> dict:
    missing = [clean(x) for x in row.get("context_missing_fields", []) if clean(x)]
    source = clean(row.get("source_name")) or "공식 원자료"
    return {
        "candidate_id": clean(row.get("candidate_id")) or clean(row.get("source_revision")),
        "title": editorial_title(row),
        "topic": editorial_title(row),
        "selection_reason": (
            f"{source}에서 시민 생활과 직접 연결되는 문제 제기가 발견됐습니다. "
            "현재 자료가 충분하지 않더라도 문제의 의미와 취재 가능성을 먼저 검토하는 후보입니다."
        ),
        "citizen_question": editorial_question(row),
        "uncommon_angle": uncommon_angle(row),
        "evidence": [{
            "source": source,
            "date": clean(row.get("source_date") or row.get("speech_date")),
            "url": clean(row.get("url")),
        }],
        "needs_verification": missing or ["발언·제안의 핵심 사실과 현재 상황 확인"],
        "source": source,
        "lane": "발견 후보",
        "evidence_status": "자료 추가 확인 필요",
        "speaker": clean(row.get("speaker")),
        "affected_group": clean(row.get("affected_group")),
        "original_signal": clean(row.get("text"))[:360],
        "score": score(row),
    }


def main() -> int:
    feed = load_feed()
    raw = list(feed.get("editorial_triage", [])) + list(feed.get("context_holds", []))
    selected, seen = [], set()
    for row in sorted(raw, key=score, reverse=True):
        if not eligible(row):
            continue
        item = make_candidate(row)
        if item["title"] in seen:
            continue
        seen.add(item["title"])
        selected.append(item)
        if len(selected) == 3:
            break

    now = datetime.now(timezone(timedelta(hours=9))).isoformat()
    payload = {
        "schema": 3,
        "generated_at_kst": now,
        "run_policy": "월·수 09:00 KST, 원자료 피드에서 최대 3건",
        "input": "source-scout-v1/output/daily_feed_latest.json",
        "count": len(selected),
        "candidates": selected,
        "lanes": {
            "discovered": "문제가 발견됐으나 자료 추가 확인이 필요한 후보",
            "verification": "독립 자료와 현장 확인이 진행 중인 후보",
            "verified": "핵심 사실과 취재 확장성이 확인된 후보",
        },
        "quality_gate": {
            "existing_items_excluded": list(EXCLUDED_MARKERS),
            "primary_source_excluded": list(SOURCE_EXCLUDED),
            "missing_data_is_not_auto_rejection": True,
            "human_review_required": True,
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = ["# 서울 기획 아이템 브리핑 v2", "", f"- 생성 시각: {now}", "- 입력: 원자료 피드", f"- 발견 후보: {len(selected)}건", ""]
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
            f"- 원 발언·신호: {item['original_signal']}",
            f"- 영향 대상: {item['affected_group'] or '확인 필요'}",
            "- 상태: 발견 후보 · 사람 검토 필요",
            f"- 추가 확인: {', '.join(item['needs_verification'])}",
            "",
        ])
    if not selected:
        lines.append("기존 검토 항목을 제외하고 현재 발견 후보가 없습니다.")
    MD_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"selected={len(selected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
