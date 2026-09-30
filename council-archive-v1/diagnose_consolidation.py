#!/usr/bin/env python3
"""One-call diagnostic for semantic candidate consolidation.

This intentionally does not archive documents or read new transcript chunks.
It inspects a fixed candidate cache so the test target cannot move.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import analyze

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent


def render(payload):
    lines = [
        "# 의회 후보 의미 통합 전용 진단",
        "",
        "- 신규 회의록 수집: 실행하지 않음",
        "- 신규 후보 생성: 실행하지 않음",
        "- OpenAI 호출: 1회",
        f"- 원자료 후보: {payload['raw_candidate_count']}건",
        f"- 1차 통합 입력: {payload['consolidation_input_count']}건",
        f"- 모델 반환 그룹: {payload['group_count']}개",
        f"- 모델 응답 완료: {'예' if payload['model_response_completed'] else '아니오'}",
        f"- 배정 완전성: {'정상' if payload['grouping_valid'] else '오류'}",
        f"- 그룹 내부 중복: {payload['duplicate_within_group_count']}건",
        f"- 그룹 간 중복 배정: {payload['duplicate_across_groups_count']}건",
        f"- 모델이 묶지 않아 단독 보존할 후보: {payload['missing_candidate_count']}건",
        f"- 대표 ID가 그룹 밖에 있음: {payload['representative_outside_group_count']}건",
    ]
    if payload["validation_error"]:
        lines.append(f"- 검증 실패: {payload['validation_error']}")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runtime",
        type=Path,
        default=ROOT / ".runtime" / "council-archive",
    )
    parser.add_argument("--output", type=Path, default=BASE / "output")
    parser.add_argument("--model", default="gpt-5.6-luna")
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required")
    candidates = analyze.load_candidate_log(
        args.runtime / "semantic_candidates.jsonl"
    )
    if len(candidates) < 2:
        raise ValueError("At least two cached candidates are required")

    review_rows = analyze.group_for_review(candidates)
    diagnostics = {
        "group_count": 0,
        "duplicate_within_group_count": 0,
        "duplicate_across_groups_count": 0,
        "missing_candidate_count": len(review_rows),
        "representative_outside_group_count": 0,
        "unknown_ids": [],
        "duplicate_across_groups": [],
        "missing_candidates": [
            row["candidate_id"] for row in review_rows[:20]
        ],
        "representative_outside_groups": [],
    }
    validation_error = ""
    grouping_valid = False
    model_response_completed = False
    try:
        answer = analyze.call_group_model(args.model, api_key, review_rows)
        model_response_completed = True
        diagnostics = analyze.grouping_diagnostics(answer, review_rows)
        analyze.validate_grouping(answer, review_rows)
        grouping_valid = True
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        validation_error = analyze.safe_error_text(exc)

    payload = {
        "schema": 1,
        "generated_at_kst": datetime.now(analyze.KST).isoformat(timespec="seconds"),
        "mode": "FIXED_CANDIDATE_CONSOLIDATION_DIAGNOSTIC",
        "model": args.model,
        "model_call_count": 1,
        "raw_candidate_count": len(candidates),
        "consolidation_input_count": len(review_rows),
        "model_response_completed": model_response_completed,
        "grouping_valid": grouping_valid,
        "validation_error": validation_error,
        **diagnostics,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    analyze.write_json(
        args.output / "consolidation_diagnostic_latest.json",
        payload,
    )
    summary = render(payload)
    (args.output / "CONSOLIDATION_DIAGNOSTIC.md").write_text(
        summary,
        encoding="utf-8",
    )
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(summary)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
