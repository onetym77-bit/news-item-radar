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


DEFAULT_EDITORIAL_LEADS = ROOT / "source-scout-v1" / "editorial-decisions" / "selected_reporting_leads.json"


def matches_selected_lead(row: dict, leads: list[dict]) -> bool:
    joined = row.get("text", "") + " " + row.get("context_text", "")
    return any(
        lead.get("anchor_text")
        and row.get("source_id") == lead.get("source_id")
        and row.get("url") == lead.get("source_url")
        and lead["anchor_text"] in joined
        for lead in leads
    )


def render_automatic_editorial_triage(feed: dict, leads: list[dict]) -> list[str]:
    """Expose strong HOLDs for human review without creating questions or transitions."""
    rows = feed.get("editorial_triage", [])
    lines = [
        "## 자동 선별 · 문맥 HOLD 편집 검토",
        "",
        "**사안·범위·영향 대상은 확인됐지만 일부 수치의 기준기간이 비어 있는 단서다. 취재 가치만 사람이 판단하며 질문 PASS·S0·기사 후보로 자동 승격하지 않는다.**",
        "",
    ]
    if not rows:
        return lines + ["- 오늘 자동 선별된 단서 없음", ""]
    for index, row in enumerate(rows, 1):
        selected = " · 기존 사람 선택과 일치" if matches_selected_lead(row, leads) else ""
        missing = ", ".join(row.get("context_missing_fields", [])) or "세부 문맥"
        lines.extend([
            f"### {index}. {md(row.get('context_subject') or row.get('text', ''), 100)}",
            "",
            f"- 자동 판정: 편집 검토 가능{selected}",
            f"- 선별 이유: {md(row.get('triage_reason', ''), 260)}",
            f"- 발언 요지(미검증): {md(row.get('text', ''), 200)}",
            f"- 아직 확인할 것: {md(missing, 140)}",
            f"- 발언자·문서일: {md(row.get('speaker', ''), 80)} · {row.get('speech_date') or '미확인'}",
            f"- [원문]({row.get('url', '')})",
            "",
        ])
    return lines


def render_editorial_review(feed: dict, leads: list[dict]) -> list[str]:
    """Show human-selected reporting leads without changing any question or article gate."""
    if not leads:
        return []
    source_rows = (
        feed.get("context_holds", [])
        + feed.get("core_discovery", [])
        + feed.get("rediscovered_carryover", [])
    )
    lines = [
        "## 편집자 지정 · 취재 착수 검토",
        "",
        "**사람이 고른 취재 단서다. 원문 발언은 주장이고 미확인 수치·피해는 사실로 확정하지 않는다. 이 영역은 A·B 기사·검증 게이트와 별개다.**",
        "",
    ]
    for lead in leads:
        anchor = lead.get("anchor_text", "")
        row = next(
            (
                item for item in source_rows
                if anchor
                and item.get("source_id") == lead.get("source_id")
                and item.get("url") == lead.get("source_url")
                and anchor in (item.get("text", "") + " " + item.get("context_text", ""))
            ),
            None,
        )
        lines.extend([f"### {md(lead.get('title', '제목 미상'), 100)}", ""])
        lines.append(f"- 편집 판단: 취재 착수 검토 · {lead.get('selected_on', '날짜 미상')} 선택")
        if row:
            missing = ", ".join(row.get("context_missing_fields", []))
            lines.append(
                f"- 원문 상태: {row.get('context_status') or '미확인'}"
                + (f" · 미확인: {md(missing, 120)}" if missing else "")
                + f" · 회의록 문서일 {row.get('speech_date') or '미확인'}"
            )
            lines.append(
                f"- 발언 요지(미검증): {md(row.get('text', ''), 180)}"
            )
        else:
            lines.append("- 원문 상태: 오늘 수집본에서 해당 발언 조각 미발견 — 원문 재확인 필요")
        lines.extend([
            f"- 취재 질문: {md(lead.get('editorial_question', ''), 220)}",
            f"- 첫 확인: {md(lead.get('first_check', ''), 220)}",
            *(
                [f"- 반대 설명 확인: {md(lead.get('countercheck', ''), 260)}"]
                if lead.get("countercheck") else []
            ),
            *(
                [f"- 지속 조건: {md(lead.get('continue_rule', ''), 260)}"]
                if lead.get("continue_rule") else []
            ),
            *(
                [f"- 축소 조건: {md(lead.get('narrow_rule', ''), 260)}"]
                if lead.get("narrow_rule") else []
            ),
            *(
                [f"- 보류 조건: {md(lead.get('stop_rule', ''), 260)}"]
                if lead.get("stop_rule") else []
            ),
            f"- [원문]({lead.get('source_url', '')})",
            "",
        ])
    return lines


def render(feed: dict, review: dict | None = None, editorial_leads: list[dict] | None = None) -> str:
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
    verification = feed.get("verification_map", [])
    selected_leads = editorial_leads or []
    lines = (
        render_automatic_editorial_triage(feed, selected_leads)
        + render_editorial_review(feed, selected_leads)
        + [
        "## C-실험. 신규 소스 질문 씨앗",
        "",
        "**아래 항목은 S0 이전 자동 탐색 결과다. 기사 후보나 검증된 사실로 간주하지 않는다.**",
        "",
        "자동 분류·수집 정렬점수와 사람의 편집 판정은 서로 다른 값이다.",
        "",
        ]
    )
    unhealthy = [
        metric
        for metric in feed.get("metrics", [])
        if not metric.get("http_ok", False)
        or str(metric.get("status_detail", "")).startswith(("FETCH_FAILED", "DEGRADED_"))
    ]
    lines.extend(["### 소스 연결·본문 상태", ""])
    if not unhealthy:
        lines.extend(["- 연결 실패나 본문 저하가 감지되지 않음", ""])
    else:
        for metric in unhealthy:
            state = metric.get("status_detail") or "FETCH_FAILED"
            detail = metric.get("error") or "본문에서 필요한 값을 확보하지 못함"
            lines.append(
                f"- {md(metric.get('name', metric.get('id', '미상')), 80)}: "
                f"{md(str(state), 60)} — {md(str(detail), 180)}"
            )
        lines.extend(
            [
                "- 위 소스의 0건은 현상 부재가 아니라 수집·본문 확인 실패로 해석",
                "",
            ]
        )
    lines.extend(
        [
        "### 핵심 발굴원 — 서울시의회 회의록",
        "",
        ]
    )
    if not core:
        lines.extend(["- 오늘 자동 기준을 통과한 문맥 잠금 완료 단서 없음", ""])
    else:
        for index, row in enumerate(core, 1):
            event = " · ".join(
                value for value in (
                    row.get("context_subject", ""),
                    row.get("context_trigger", ""),
                ) if value
            )
            claim_level = CLAIM_STATUS_LABELS.get(
                row.get("claim_status", ""),
                row.get("claim_status") or "확인 수준 미분류",
            )
            source_level = " · ".join(
                value for value in (
                    row.get("speaker", ""),
                    row.get("speech_type_label", ""),
                    claim_level,
                    METRIC_SOURCE_LABELS.get(
                        row.get("metric_source_status", ""),
                        row.get("metric_source_status", ""),
                    ),
                ) if value
            )
            period_level = METRIC_PERIOD_LABELS.get(
                row.get("metric_period_status", ""),
                row.get("metric_period_status") or "미확인",
            )
            fact_label = row.get("statement_label") or "제시된 내용"
            lines.extend(
                [
                    f"#### {index}. {row.get('context_subject') or '문맥 잠금 완료 단서'}",
                    "",
                    f"- 무슨 일: {md(event or '사안 미확인', 240)}",
                    f"- 적용 범위: {md(row.get('sector_scope') or '확인 필요', 260)}",
                    f"- 영향 확인 대상: {md(row.get('affected_group') or '확인 필요', 180)}",
                    f"- {fact_label}: {md(row.get('display_fact') or row.get('question_basis') or row.get('text', ''), 300)}",
                    (
                        f"- 수치 범위·기준: {md(row.get('metric_scope') or '정량 수치 없음', 240)} · "
                        f"{row.get('metric_period') or '확인 필요'} ({period_level})"
                    ),
                    f"- 출처·확인 수준: {md(source_level or row.get('source_name', '미상'), 220)}",
                    f"- 회의록 문서일: {row.get('speech_date') or '미확인'}",
                    f"- 범위 주의: {md(row.get('scope_exclusion') or '별도 주의 없음', 180)}",
                    f"- 기획 질문: {md(row.get('question', ''), 300)}",
                    f"- 질문 일치: {row.get('grounding_status', 'HOLD')} · 수집 정렬점수 {row.get('score', 0)}",
                    f"- [원문]({row.get('url', '')})",
                    "",
                ]
            )

    lines.extend(["### 문맥 확인 대기 — 질문 생성 금지", ""])
    if not context_holds:
        lines.extend(["- 사건·대상·수치 범위·기준기간을 확정하지 못해 보류된 의회 단서 없음", ""])
    else:
        for row in context_holds:
            missing = ", ".join(row.get("context_missing_fields", [])) or "세부 문맥"
            lines.extend(
                [
                    f"- 발언 조각: {md(row.get('text', ''), 220)}",
                    f"- 보류 이유: {md(row.get('context_reason') or '문맥 잠금 미완료', 220)}",
                    f"- 빠진 항목: {md(missing, 160)}",
                    f"- 회의록 문서일: {row.get('speech_date') or '미확인'}",
                    f"- [원문]({row.get('url', '')})",
                    "",
                ]
            )

    lines.extend(["### 보완 발굴원", ""])
    if not auxiliary:
        lines.extend(["- 오늘 자동 기준을 통과한 보완 발굴 단서 없음", ""])
    else:
        for row in auxiliary:
            lines.extend(
                [
                    f"- 출처: {row.get('source_name', row.get('source_id', '미상'))}",
                    f"- 단서: {md(row.get('text', ''))}",
                    f"- 근거 앵커: {row.get('evidence_anchor', 'NONE')}",
                    f"- 신선도 기준일: {row.get('source_date') or '미상'} · {row.get('freshness_basis') or '기준 미상'} · 경과 {row.get('freshness_days', '미상')}일",
                    f"- 질문: {md(row.get('question', ''))}",
                    f"- [원문]({row.get('url', '')})",
                    "",
                ]
            )

    lines.extend(["### 서울 지역화 대기 — 서울 근거 확보 전 S0 불가", ""])
    if not localization:
        lines.extend(["- 오늘 서울 자료로 재확인할 전국 단서 없음", ""])
    else:
        for row in localization:
            lines.extend(
                [
                    f"- 전국 단서: {md(row.get('question_basis') or row.get('text', ''), 220)}",
                    f"- 서울 검증 질문: {md(row.get('question', ''), 220)}",
                    f"- 출처: {row.get('source_name', row.get('source_id', '미상'))}",
                    f"- 신선도 기준일: {row.get('source_date') or '미상'} · {row.get('freshness_status') or 'FRESHNESS_UNKNOWN'}",
                    f"- [원문]({row.get('url', '')})",
                    "- 상태: 서울 수치 미확보 — 편집 카드·S0 전이 대상 아님",
                    "",
                ]
            )

    lines.extend(["### 동일 원문 재등장 — 오늘 새 후보 제외", ""])
    if not rediscovered:
        lines.extend(["- 이전 실행과 동일한 원문·날짜의 재등장 없음", ""])
    else:
        for row in rediscovered:
            lines.append(
                f"- {md(row.get('question_basis') or row.get('text', ''), 190)} — "
                "이전과 같은 원문 지문; 새 카드·자동 재활성화·S0 제안 제외"
            )
        lines.append("")
    lines.extend(["### STALE_CARRYOVER — 오늘 후보 제외", ""])
    if not stale:
        lines.extend(["- 신선도 창을 넘긴 유효 단서 없음", ""])
    else:
        for row in stale:
            lines.append(
                f"- {md(row.get('question_basis') or row.get('text', ''), 190)} — "
                f"{row.get('source_date', '날짜 미상')} 기준 {row.get('freshness_days', '?')}일 경과; "
                "오늘 카드·재활성화·S0 제안 제외"
            )
        lines.append("")

    lines.extend(["### 보관 종료 단서 — 감사용 표본", ""])
    if not archived:
        lines.extend(["- 보관 기한을 넘긴 유효 단서 표본 없음", ""])
    else:
        for row in archived:
            lines.append(
                f"- {md(row.get('question_basis') or row.get('text', ''), 190)} — "
                f"{row.get('source_date', '날짜 미상')} 기준 {row.get('freshness_days', '?')}일 경과; "
                f"오늘 후보 제외 · [원문]({row.get('url', '')})"
            )
        lines.append("")

    lines.extend(["### 날짜 확인 대기 — 오늘 후보 제외", ""])
    if not freshness_holds:
        lines.extend(["- 날짜를 확인하지 못한 유효 단서 없음", ""])
    else:
        for row in freshness_holds:
            lines.append(
                f"- {md(row.get('question_basis') or row.get('text', ''), 190)} — "
                f"{row.get('freshness_status', 'FRESHNESS_UNKNOWN')}; 원문 날짜 확인 전 후보 제외"
            )
        lines.append("")
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
                f"(자료일 {row.get('source_date') or '미상'} · {row.get('freshness_status') or 'FRESHNESS_UNKNOWN'}) "
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
                f"(자료일 {row.get('source_date') or '미상'} · {row.get('freshness_status') or 'FRESHNESS_UNKNOWN'}) "
                f"([원문]({row.get('url', '')}))"
            )
        lines.append("")

    lines.extend(["### 검증 데이터 지도", ""])
    if not verification:
        lines.extend(["- 오늘 연결할 검증 자료 없음", ""])
    else:
        lines.extend(
            [
                "| 자료 단서 | 자료일·상태 | 사용할 때 | 원문 |",
                "|---|---|---|---|",
            ]
        )
        for row in verification:
            lines.append(
                f"| {md(row.get('text', ''), 140)} | "
                f"{row.get('source_date') or '미상'} · {row.get('freshness_status') or 'FRESHNESS_UNKNOWN'} | "
                f"{md(row.get('question', ''), 120)} | [원문]({row.get('url', '')}) |"
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
    parser.add_argument("--editorial-leads", type=Path, default=DEFAULT_EDITORIAL_LEADS)
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
    editorial_leads = (
        json.loads(args.editorial_leads.read_text(encoding="utf-8")).get("leads", [])
        if args.editorial_leads.is_file() else []
    )
    section = render(feed, review, editorial_leads)
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
