#!/usr/bin/env python3
"""Record a human decision for an exact YouTube shadow card."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from build_youtube_review_queue import DECISIONS, QUEUE, validate_queue

VALID_DECISIONS = {"PROMISING", "HOLD", "DISCARD"}


def record(proposal_id, decision, note, *, queue_path=QUEUE, decisions_path=DECISIONS):
    if decision not in VALID_DECISIONS:
        raise ValueError("알 수 없는 판정")
    queue = validate_queue(json.loads(queue_path.read_text(encoding="utf-8")))
    items = {str(item["id"]): item for item in queue["items"]}
    if proposal_id not in items:
        raise ValueError("현재 유튜브 신호 검토 큐에 없는 ID")
    try:
        history = json.loads(decisions_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        history = []
    if not isinstance(history, list):
        raise ValueError("지원하지 않는 유튜브 신호 판정 이력")
    if any(str(item.get("id")) == proposal_id for item in history):
        raise ValueError("이미 판정한 ID")
    item = items[proposal_id]
    row = {
        "id": proposal_id,
        "decision": decision,
        "note": " ".join(note.split())[:500],
        "title": item["title"],
        "source": item["source"],
        "url": item["url"],
        "decided_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    history.append(row)
    decisions_path.parent.mkdir(parents=True, exist_ok=True)
    decisions_path.write_text(
        json.dumps(history[-200:], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return row


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    parser.add_argument("--decision", choices=sorted(VALID_DECISIONS), required=True)
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    print(json.dumps(record(args.id, args.decision, args.note), ensure_ascii=False))
