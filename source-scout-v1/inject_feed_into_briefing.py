#!/usr/bin/env python3
"""Insert the experimental source feed into the daily briefing.

The inserted records are explicitly marked pre-S0 and do not alter the item ledger.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BRIEFING = ROOT / "daily-briefing-v5" / "output" / "briefing_latest.md"
DEFAULT_FEED = ROOT / "source-scout-v1" / "output" / "daily_feed_latest.json"
DEFAULT_REVIEW = ROOT / "source-scout-v1" / "output" / "editorial_review_cards_latest.json"
INSERT_BEFORE = "## C. 새 질문 원석·후속 관찰"


def md(value: str, limit: int = 180) -> str:
    value = " ".join((value or "").split()).replace("|", "·")
    if len(value) > limit:
        value = value[: limit - 1].rstrip() + "…"
    return value


CLAIM_STATUS_LABELS = {
    "ATTRIBUTED_CLAIM": "의원 발언에서 제시",
    "OBSERVED_OR_PUBLISHED": "원자료에 공개된 값",
    "UNRESOLVED": "확인 수준 미분류",
}
METRIC_SOURCE_LABELS = {
    "SPEAKER_ONLY": "산정 원자료 미확인",
    "CITED_SOURCE_UNCHECKED": "인용 원자료 대조 전",
    "INDEPENDENTLY_VERIFIED": "원자료 재확인 완료",
}
METRIC_PERIOD_LABELS = {
    "EXPLICIT": "발언문에 기간 명시",
    "RELATIVE_TO_DOCUMENT": "발언 당시 기준",
    "UNKNOWN": "기준기간 확인 필요",
    "NOT_APPLICABLE": "정량 수치 없음",
}


def render(feed: dict, review: dict | None = None) -> str:
    """Render only editorial decisions; keep evidence excerpts in diagnostic files."""
    review = review or {}
    core = feed.get("core_discovery", [])
    auxiliary = feed.get("auxiliary_discovery", [])
    localization = feed.get("localization_discovery", [])
    rediscovered = feed.get("rediscovered_carryover", [])
    stale = feed.get("stale_carryover", [])
    archived = feed.get("archived_stale", [])
    freshness_holds = feed.get("freshness_holds", [])
    context_holds = feed.get("context_holds", [])
    baselines = feed.get("activity_baselines", [])
    metadata_leads = feed.get("verification_metadata_leads", [])
    schema_leads = feed.get("verification_schema_leads", [])
    candidates = core + auxiliary
    proposals = review.get("transition_proposals", [])
    killer = review.get("killer_test")
    legacy = review.get("legacy_rereview", [])

    unhealthy = [
        metric
        for metric in feed.get("metrics", [])
        if not metric.get("http_ok", False)
        or str(metric.get("status_detail", "")).startswith(("FETCH_FAILED", "DEGRADED_"))
    ]
    hold_counts = [
        ("문맥 미확정", len(context_holds)),
        ("이미 본 원문", len(rediscovered)),
        ("신선도 초과", len(stale)),
        ("보관 종료", len(archived)),
        ("날짜 미확인", len(freshness_holds)),
        ("활동량 기준선", len(baselines)),
        ("실제 값 미확인 데이터", len(metadata_leads) + len(schema_leads)),
    ]
    largest_hold = max(hold_counts, key=lambda item: item[1], default=("없음", 0))

    lines = [
        "## C-실험. 신규 소스 발굴 요약",
        "",
        "### 한줄 판단",
        "",
    ]
    if candidates:
        lines.append(
            f"**오늘 사람이 검토할 새 질문 후보는 {len(candidates)}건입니다.** "
            "자동으로 아이템 장부나 S0 단계에 올리지는 않습니다."
        )
    else:
        reason = (
            f"가장 큰 병목은 {largest_hold[0]} {largest_hold[1]}건입니다."
            if largest_hold[1]
            else "수집된 자료에서 질문 후보를 만들지 못했습니다."
        )
        lines.append(f"**오늘 새 질문 후보는 없습니다.** {reason}")
    lines.extend(
        [
            "",
            f"- 새 질문 후보: {len(candidates)}건",
            f"- 서울 근거 확인 대기: {len(localization)}건",
            f"- 사람의 S0 전이 승인 대기: {len(proposals)}건",
            "",
            "### 오늘 검토할 후보",
            "",
        ]
    )
    if not candidates:
        lines.extend(["- 없음", ""])
    else:
        for index, row in enumerate(candidates[:5], 1):
            title = (
                row.get("context_subject")
                or row.get("source_name")
                or row.get("source_id")
                or f"후보 {index}"
            )
            question = row.get("question") or "검증 질문 미작성"
            source_date = row.get("speech_date") or row.get("source_date") or "날짜 미확인"
            lines.extend(
                [
                    f"#### {index}. {md(title, 100)}",
                    "",
                    f"- 기획 질문: {md(question, 300)}",
                    f"- 출처·자료일: {md(row.get('source_name') or row.get('source_id') or '미상', 100)} · {source_date}",
                    f"- [원문]({row.get('url', '')})",
                    "",
                ]
            )
        if len(candidates) > 5:
            lines.extend([f"- 나머지 {len(candidates) - 5}건은 진단 파일에서 확인", ""])

    lines.extend(["### 서울 근거 확인 대기", ""])
    if not localization:
        lines.extend(["- 없음", ""])
    else:
        for row in localization[:3]:
            lines.append(
                f"- {md(row.get('question') or row.get('context_subject') or '질문 미작성', 240)} "
                f"([원문]({row.get('url', '')}))"
            )
        if len(localization) > 3:
            lines.append(f"- 외 {len(localization) - 3}건")
        lines.append("")

    lines.extend(["### 보류 요약", ""])
    nonzero_holds = [(label, count) for label, count in hold_counts if count]
    if not nonzero_holds:
        lines.extend(["- 보류 항목 없음", ""])
    else:
        lines.append("- " + " · ".join(f"{label} {count}건" for label, count in nonzero_holds))
        lines.append(
            "- 발언 조각·근거 문장·중복 원문·오래된 단서의 상세 내용은 브리핑에서 제외했습니다."
        )
        lines.append("")

    lines.extend(["### 수집 이상", ""])
    if not unhealthy:
        lines.extend(["- 없음", ""])
    else:
        for metric in unhealthy:
            state = metric.get("status_detail") or "FETCH_FAILED"
            lines.append(
                f"- {md(metric.get('name', metric.get('id', '미상')), 80)}: "
                f"{md(str(state), 80)}"
            )
        lines.extend(
            [
                "- 이 소스의 0건은 현상 부재가 아니라 수집·본문 확인 실패로 봅니다.",
                "",
            ]
        )

    lines.extend(["### 다음 편집 판단", ""])
    lines.append(f"- S0 전이 승인 대기: {len(proposals)}건 — 자동 반영 없음")
    if killer:
        lines.append(
            f"- 우선 검증: {md(killer.get('test_question') or killer.get('candidate_id', ''), 240)}"
        )
        lines.append(f"- 통과선: {md(killer.get('test_pass_rule', ''), 180)}")
        lines.append(f"- 폐기선: {md(killer.get('test_kill_rule', ''), 180)}")
    else:
        lines.append("- 우선 검증: 완전한 판정선이 입력된 항목 없음")
    if legacy:
        missing = sum(row.get("source_status") == "SOURCE_REQUIRED" for row in legacy)
        lines.append(f"- 기존 질문 재심사: {len(legacy)}건 · 원자료 복구 필요 {missing}건")
    lines.extend(
        [
            "",
            "- 편집 판정은 source-scout-v1/HUMAN_REVIEW_QUEUE.csv에 기록합니다.",
            "- 전체 근거와 수집 진단은 별도 source-scout 산출물에만 보존합니다.",
            "",
        ]
    )
    return "\n".join(lines)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--briefing", type=Path, default=DEFAULT_BRIEFING)
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.feed.is_file():
        print(f"source feed missing; briefing unchanged: {args.feed}")
        return 0
    text = args.briefing.read_text(encoding="utf-8")
    if INSERT_BEFORE not in text:
        raise RuntimeError(f"briefing insertion point missing: {INSERT_BEFORE}")
    feed = json.loads(args.feed.read_text(encoding="utf-8"))
    review = json.loads(args.review.read_text(encoding="utf-8")) if args.review.is_file() else {}
    section = render(feed, review)
    text = text.replace(INSERT_BEFORE, section + "\n" + INSERT_BEFORE, 1)
    args.briefing.write_text(text, encoding="utf-8")

    history_path = (
        args.briefing.parent
        / "history"
        / f"briefing_{feed['generated_at_kst'][:10]}.md"
    )
    if history_path.is_file():
        history_path.write_text(text, encoding="utf-8")
    print(f"injected={args.briefing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
