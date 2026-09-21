#!/usr/bin/env python3
"""Summarize seven-day human precision for experimental source leads."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_QUEUE = HERE / "HUMAN_REVIEW_QUEUE.csv"
DEFAULT_MD = HERE / "output" / "review_summary_latest.md"
DEFAULT_JSON = HERE / "output" / "review_summary_latest.json"
VALID_LABELS = {"PROMISING", "VERIFY", "NOISE", "DUPLICATE"}
POSITIVE_LABELS = {"PROMISING"}
USEFUL_LABELS = {"PROMISING", "VERIFY"}


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100, 1) if denominator else None


def percent_text(value: float | None) -> str:
    return "판정 대기" if value is None else f"{value}%"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--as-of", type=date.fromisoformat)
    parser.add_argument("--days", type=int, default=7)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    as_of = args.as_of or date.today()
    start = as_of - timedelta(days=max(args.days - 1, 0))
    raw_rows = [
        row
        for row in read_rows(args.queue)
        if start.isoformat() <= row.get("first_seen", "") <= as_of.isoformat()
        and (
            row.get("review_eligible", "").strip().lower() == "true"
            or (
                not row.get("review_eligible", "").strip()
                and row.get("auto_active_today", "").strip().lower() == "true"
            )
        )
    ]
    families = {}
    for row in raw_rows:
        family = "|".join([
            row.get("source_id", "").strip(),
            row.get("context_subject", "").strip(),
            row.get("central_question", "").strip() or row.get("question", "").strip(),
        ])
        if family.strip("|"):
            families[family] = row
    rows = list(families.values()) if families else raw_rows
    labeled = [
        row for row in rows if row.get("editor_judgment", "").strip().upper() in VALID_LABELS
    ]
    promising = sum(row.get("editor_judgment", "").strip().upper() in POSITIVE_LABELS for row in labeled)
    useful = sum(row.get("editor_judgment", "").strip().upper() in USEFUL_LABELS for row in labeled)

    source_ids = sorted({row.get("source_id", "") for row in rows if row.get("source_id")})
    by_source = {}
    for source_id in source_ids:
        source_rows = [row for row in rows if row.get("source_id") == source_id]
        source_labeled = [
            row for row in source_rows
            if row.get("editor_judgment", "").strip().upper() in VALID_LABELS
        ]
        source_promising = sum(
            row.get("editor_judgment", "").strip().upper() == "PROMISING"
            for row in source_labeled
        )
        source_useful = sum(
            row.get("editor_judgment", "").strip().upper() in USEFUL_LABELS
            for row in source_labeled
        )
        by_source[source_id] = {
            "generated": len(source_rows),
            "labeled": len(source_labeled),
            "promising": source_promising,
            "useful": source_useful,
            "precision": ratio(source_promising, len(source_labeled)),
            "useful_rate": ratio(source_useful, len(source_labeled)),
        }

    summary = {
        "period": {"start": start.isoformat(), "end": as_of.isoformat(), "days": args.days},
        "generated": len(rows),
        "labeled": len(labeled),
        "coverage": ratio(len(labeled), len(rows)),
        "promising": promising,
        "useful": useful,
        "precision": ratio(promising, len(labeled)),
        "useful_rate": ratio(useful, len(labeled)),
        "by_source": by_source,
        "labels": {
            "PROMISING": "새 질문과 4시간 검증 경로가 모두 있는 강한 씨앗",
            "VERIFY": "즉시 기사는 아니지만 추가 확인 가치가 있는 씨앗",
            "NOISE": "일반 발표·정치적 주장·안내 수준",
            "DUPLICATE": "기존 질문 가족과 동일",
        },
    }

    DEFAULT_MD.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 신규 소스 7일 편집 정밀도",
        "",
        f"- 기간: {start.isoformat()} ~ {as_of.isoformat()}",
        f"- 생성 후보: {len(rows)}건",
        f"- 사람 판정 완료: {len(labeled)}건 ({summary['coverage'] if summary['coverage'] is not None else '-'}%)",
        f"- 강한 질문 씨앗 정밀도: {percent_text(summary['precision'])}",
        f"- 추가 확인 가치 포함 유효율: {percent_text(summary['useful_rate'])}",
        "",
        "## 소스별",
        "",
        "| 소스 | 생성 | 판정 | 강한 씨앗 | 확인 가치 포함 | 정밀도 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for source_id, item in by_source.items():
        lines.append(
            f"| {source_id} | {item['generated']} | {item['labeled']} | {item['promising']} | "
            f"{item['useful']} | {percent_text(item['precision'])} |"
        )
    lines.extend(
        [
            "",
            "판정 완료율이 80% 미만이면 소스 정밀도 결론을 내리지 않는다.",
            "",
        ]
    )
    DEFAULT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"summary={DEFAULT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
