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
INSERT_BEFORE = "## C. 새 질문 원석·후속 관찰"


def md(value: str, limit: int = 180) -> str:
    value = " ".join((value or "").split()).replace("|", "·")
    if len(value) > limit:
        value = value[: limit - 1].rstrip() + "…"
    return value


def render(feed: dict) -> str:
    core = feed.get("core_discovery", [])
    auxiliary = feed.get("auxiliary_discovery", [])
    verification = feed.get("verification_map", [])
    lines = [
        "## C-실험. 신규 소스 질문 씨앗",
        "",
        "**아래 항목은 S0 이전 자동 탐색 결과다. 기사 후보나 검증된 사실로 간주하지 않는다.**",
        "",
        "### 핵심 발굴원 — 서울시의회 회의록",
        "",
    ]
    if not core:
        lines.extend(["- 오늘 자동 기준을 통과한 질문 씨앗 없음", ""])
    else:
        lines.extend(
            [
                "| 관찰 단서 | 붙일 질문 | 점수 | 원문 |",
                "|---|---|---:|---|",
            ]
        )
        for row in core:
            lines.append(
                f"| {md(row.get('text', ''))} | {md(row.get('question', ''))} | "
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
                    f"- 질문: {md(row.get('question', ''))}",
                    f"- [원문]({row.get('url', '')})",
                    "",
                ]
            )

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
    section = render(feed)
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
