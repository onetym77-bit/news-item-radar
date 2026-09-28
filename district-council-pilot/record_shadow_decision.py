#!/usr/bin/env python3
"""Record an editor decision for an exact district-council shadow card."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "district-council-pilot" / "output" / "recent-l3" / "editorial_review_queue.json"
DECISIONS = ROOT / "district-council-pilot" / "output" / "recent-l3" / "editor_decisions.json"
VALID_DECISIONS = {"PROMISING", "HOLD", "DISCARD"}


def record(proposal_id, decision, note, *, queue_path=QUEUE, decisions_path=DECISIONS):
    if decision not in VALID_DECISIONS:
        raise ValueError("알 수 없는 판정")
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    if queue.get("schema") != 1 or not isinstance(queue.get("items"), list):
        raise ValueError("지원하지 않는 구의회 검토 큐")
    items = {str(item.get("id")): item for item in queue["items"] if item.get("id")}
    if proposal_id not in items:
        raise ValueError("현재 구의회 검토 큐에 없는 ID")
    try:
        history = json.loads(decisions_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        history = []
    if not isinstance(history, list):
        raise ValueError("지원하지 않는 구의회 판정 이력")
    if any(str(item.get("id")) == proposal_id for item in history):
        raise ValueError("이미 판정한 ID")
    item = items[proposal_id]
    decision_row = {
        "id": proposal_id,
        "decision": decision,
        "note": note.strip()[:500],
        "title": item.get("title", ""),
        "issue_key": item.get("issue_key", ""),
        "source": item.get("source", ""),
        "url": item.get("url", ""),
        "decided_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    history.append(decision_row)
    decisions_path.parent.mkdir(parents=True, exist_ok=True)
    decisions_path.write_text(
        json.dumps(history[-200:], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return decision_row


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    parser.add_argument(
        "--decision",
        choices=["PROMISING", "HOLD", "DISCARD"],
        required=True,
    )
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    print(json.dumps(record(args.id, args.decision, args.note), ensure_ascii=False))
