#!/usr/bin/env python3
"""Replay human labels against one immutable substantive-comparison artifact.

This script never fetches sources. The artifact's bounded, redacted cards are
the fixed denominator; a later live crawl cannot silently change the sample.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from compare_substantive_samples import (
    SAMPLE_SIZE, SOURCE_IDS, attach_reviews, read_reviews, source_metrics,
    validate_payload,
)

BASE = Path(__file__).resolve().parent
TRIAL = "SUBSTANTIVE_BODY_SOURCE_COMPARISON"


def load_snapshot(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    payload = json.loads(raw.decode("utf-8-sig"))
    if payload.get("schema") != 1 or payload.get("trial") != TRIAL:
        raise ValueError("not a substantive-comparison snapshot")
    if payload.get("sample_size_per_source") != SAMPLE_SIZE:
        raise ValueError("snapshot sample size differs from the review contract")
    if payload.get("question_output") != "NONE" or payload.get("briefing_output") != "NONE":
        raise ValueError("snapshot would cross an editorial gate")
    if payload.get("automatic_ledger_write") is not False:
        raise ValueError("snapshot would write to the item ledger")
    errors = validate_payload(payload)
    if errors:
        raise ValueError("; ".join(errors))
    cards = payload["cards"]
    if any(card.get("human_label") for card in cards):
        raise ValueError("snapshot already contains labels; use the original collection artifact")
    return payload, digest


def evaluate(snapshot: dict, digest: str, reviews_path: Path) -> dict:
    cards = copy.deepcopy(snapshot["cards"])
    reviews = read_reviews(reviews_path, cards)
    attach_reviews(cards, reviews)
    metrics = [source_metrics(cards, source_id) for source_id in SOURCE_IDS]
    return {
        "schema": 1,
        "trial": "FROZEN_SUBSTANTIVE_HUMAN_REVIEW",
        "source_snapshot_sha256": digest,
        "source_collected_at_kst": snapshot["collected_at_kst"],
        "sample_size_per_source": SAMPLE_SIZE,
        "question_output": "NONE",
        "briefing_output": "NONE",
        "automatic_ledger_write": False,
        "raw_bodies_persisted": 0,
        "cards": cards,
        "metrics": metrics,
        "human_review_count": len(reviews),
        "interpretation_status": (
            "PILOT_DESCRIPTIVE_ONLY"
            if all(row["sample_count"] == SAMPLE_SIZE and row["reviewed_count"] == SAMPLE_SIZE for row in metrics)
            else "HUMAN_REVIEW_INCOMPLETE"
        ),
        "source_winner": None,
    }


def render(result: dict) -> str:
    names = {
        "seoul_audit_results": "서울시 감사 결과",
        "citizen_proposals": "상상대로 서울 시민제안",
    }
    lines = [
        "# 고정 표본 사람 판정 결과",
        "",
        f"- 원본 수집: {result['source_collected_at_kst']}",
        f"- 고정 표본 SHA-256: {result['source_snapshot_sha256']}",
        "- 후속 재수집 없이 원본 3건씩에만 사람 판정을 결합했습니다.",
        "- 이 표본은 흐름 검증용입니다. 3건씩의 비율로 우수 소스나 운영 편입을 결정하지 않습니다.",
        "",
        "| 소스 | 확보 | 판정 | PROMISING | VERIFY | NOISE | 중복 | 읽기 실패 | 유효 단서율(판정분모) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["metrics"]:
        rate = "-" if row["useful_signal_rate"] is None else f"{row['useful_signal_rate'] * 100:.0f}%"
        lines.append(
            f"| {names[row['source_id']]} | {row['sample_count']} | {row['reviewed_count']} | "
            f"{row['promising_count']} | {row['verify_count']} | {row['noise_count']} | "
            f"{row['duplicate_count']} | {row['unreadable_count']} | {rate} |"
        )
    lines.extend(["", "## 항목별 판정", ""])
    for card in result["cards"]:
        lines.append(
            f"- {names[card['source_id']]} · [{card['title']}]({card['detail_url']}) "
            f"→ {card['human_label'] or '판정 대기'}"
        )
    lines.extend([
        "",
        f"- 상태: {result['interpretation_status']}",
        "- 감사 문서는 여러 지적이 묶인 단위이고 시민제안은 한 사람의 미확인 제안입니다. 두 비율을 생산성 순위로 직접 읽지 않습니다.",
        "- 질문·일일 브리핑·아이템 장부는 변경하지 않았습니다.",
        "",
    ])
    return "\n".join(lines)


def run(snapshot_path: Path, reviews_path: Path, output_dir: Path) -> dict:
    if not reviews_path.is_file():
        raise FileNotFoundError("human review CSV not found")
    snapshot, digest = load_snapshot(snapshot_path)
    result = evaluate(snapshot, digest, reviews_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "review_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = render(result)
    (output_dir / "REVIEW_SUMMARY.md").write_text(summary, encoding="utf-8")
    print(summary)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-json", type=Path, required=True)
    parser.add_argument("--reviews-csv", type=Path, default=BASE / "substantive_reviews_2026-09-17.csv")
    parser.add_argument("--output-dir", type=Path, default=BASE / "output" / "substantive-human-review")
    args = parser.parse_args()
    run(args.snapshot_json, args.reviews_csv, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
