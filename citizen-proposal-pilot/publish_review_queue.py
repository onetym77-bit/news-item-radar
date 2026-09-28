#!/usr/bin/env python3
"""Merge a validated citizen-signal artifact into the public pending queue."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from build_review_queue import DECISIONS, QUEUE, validate_queue

def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"읽을 수 없는 JSON: {path}") from exc

def publish(candidate: dict, current: dict, decisions: list[dict]) -> dict:
    validate_queue(candidate)
    validate_queue(current)
    if not isinstance(decisions, list):
        raise ValueError("지원하지 않는 시민 신호 판정 이력")
    decided = {
        str(row.get("id")) for row in decisions
        if row.get("decision") in {"PROMISING", "HOLD", "DISCARD"}
    }
    by_id = {
        item["id"]: item for item in current["items"]
        if item["id"] not in decided
    }
    for item in candidate["items"]:
        if item["id"] not in decided:
            by_id[item["id"]] = item
    items = list(by_id.values())[-50:]
    if items == current["items"]:
        return current
    return validate_queue({
        "schema": 1,
        "mode": "CITIZEN_SIGNAL_SHADOW",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "items": items,
    })

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--current", type=Path, default=QUEUE)
    parser.add_argument("--decisions", type=Path, default=DECISIONS)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    candidate = load(args.candidate, None)
    current = load(args.current, None)
    decisions = load(args.decisions, [])
    result = publish(candidate, current, decisions)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"published_pending": len(result["items"])}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
