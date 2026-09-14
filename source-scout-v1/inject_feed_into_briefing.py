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


def render(feed: dict, review: dict | None = None) -> str:
    review = review or {}
    core = feed.get("core_discovery", [])
    auxiliary = feed.get("auxiliary_discovery", [])
    baselines = feed.get("activity_baselines", [])
    metadata_leads = feed.get("verification_metadata_leads", [])
    schema_leads = feed.get("verification_schema_leads", [])
    verification = feed.get("verification_map", [])
    lines = [
        "## C-실험. 신규 소스 질문 씨앗",
        "",
        "**아래 항목은 S0 이전 자동 탐색 결과다. 기사 후보나 검증된 사실로 간주하지 않는다.**",
        "",
        "자동 분류·수집 정렬점수와 사람의 편집 판정은 서로 다른 값이다.",
        "",
        "### 핵심 발굴원 — 서울시의회 회의록",
        "",
    ]
    if not core:
        lines.extend(["- 오늘 자동 기준을 통과한 질문 씨앗 없음", ""])
    else:
        lines.extend(
            [
                "| 관찰된 사실 | 자동 앵커 | 붙일 질문 | 질문 일치 | 수집 정렬점수 | 원문 |",
                "|---|---|---|---|---:|---|",
            ]
        )
        for row in core:
            lines.append(
                f"| {md(row.get('question_basis') or row.get('text', ''))} | "
                f"{row.get('evidence_anchor', 'NONE')} · {row.get('claim_status', 'UNRESOLVED')} | "
                f"{md(row.get('question', ''))} | {row.get('grounding_status', 'HOLD')} | "
                f"{row.get('score', 0)} | [원문]({row.get('url', '')}) |"
            )
        lines.append("")

    lines.extend(["### 보조 발굴원 — 서울시 응답소", ""])
    if not auxiliary:
        lines.extend(["- 오늘 자동 기준을 통과한 시민 경험 단서 없음", ""])
    else:
        for row in auxiliary:
            lines.extend(
                [
                    f"- 단서: {md(row.get('text', ''))}",
                    f"- 근거 앵커: {row.get('evidence_anchor', 'NONE')}",
                    f"- 질문: {md(row.get('question', ''))}",
                    f"- [원문]({row.get('url', '')})",
                    "",
                ]
            )

    lines.extend(["### 활동량 기준선 — 후보 아님", ""])
    if not baselines:
        lines.extend(["- 오늘 저장된 활동량 기준선 없음", ""])
    else:
        for row in baselines:
            lines.append(
                f"- {md(row.get('text', ''), 180)} — 전일·전월 누적 비교 전에는 이상 신호로 사용하지 않음"
            )
        lines.append("")

    lines.extend(["### 데이터 구조 확인 — 실제 값 미수집", ""])
    if not schema_leads:
        lines.extend(["- 오늘 구조만 확인된 데이터셋 없음", ""])
    else:
        for row in schema_leads:
            lines.append(
                f"- {md(row.get('text', ''), 170)} — 실제 데이터 행 수집 전 검증 자산 사용 금지 "
                f"([원문]({row.get('url', '')}))"
            )
        lines.append("")

    lines.extend(["### 데이터셋 후보 — 스키마·값 미확인", ""])
    if not metadata_leads:
        lines.extend(["- 오늘 스키마 확인 대기 중인 데이터셋 제목 없음", ""])
    else:
        for row in metadata_leads:
            lines.append(
                f"- {md(row.get('text', ''), 160)} — 컬럼·실제 값 확인 전 검증 자산 사용 금지 "
                f"([원문]({row.get('url', '')}))"
            )
        lines.append("")

    lines.extend(["### 검증 데이터 지도", ""])
    if not verification:
        lines.extend(["- 오늘 연결할 검증 자료 없음", ""])
    else:
        lines.extend(
            [
                "| 자료 단서 | 사용할 때 | 원문 |",
                "|---|---|---|",
            ]
        )
        for row in verification:
            lines.append(
                f"| {md(row.get('text', ''), 140)} | {md(row.get('question', ''), 120)} | "
                f"[원문]({row.get('url', '')}) |"
            )
        lines.append("")

    proposals = review.get("transition_proposals", [])
    killer = review.get("killer_test")
    legacy = review.get("legacy_rereview", [])
    lines.extend(["### 사람 판정 이후", ""])
    lines.append(f"- S0 전이 승인 대기: {len(proposals)}건 — 자동 반영 없음")
    if killer:
        lines.extend(
            [
                f"- 오늘의 킬러 테스트: {killer.get('candidate_id', '-')}",
                f"- 테스트 질문: {md(killer.get('test_question', ''), 220)}",
                f"- 통과선: {md(killer.get('test_pass_rule', ''), 180)}",
                f"- 폐기선: {md(killer.get('test_kill_rule', ''), 180)}",
                "- 상태: PLANNED — 아직 수행하지 않음",
            ]
        )
    else:
        lines.append("- 오늘의 킬러 테스트: 완전한 판정선이 입력된 항목 없음")
    if legacy:
        missing = sum(row.get("source_status") == "SOURCE_REQUIRED" for row in legacy)
        lines.append(f"- 기존 질문 재심사: {len(legacy)}건 · 원자료 복구 필요 {missing}건")
    lines.append("")
    lines.extend(
        [
            "- 편집 판정 기록: source-scout-v1/HUMAN_REVIEW_QUEUE.csv",
            "- 자동 점수 통과는 검증 큐 진입 검토만 허용하며 ITEM_LEDGER에는 자동 등록하지 않음",
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
