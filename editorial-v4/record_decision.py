#!/usr/bin/env python3
"""Record an editor's disposition for an exact saved proposal ID."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "editorial-v4/output/latest.json"
DECISIONS = ROOT / "editorial-v4/decisions.json"

def record(proposal_id, decision, note):
    if decision not in {"COMPLETE", "DISCARD", "HOLD"}:
        raise ValueError("알 수 없는 판정")
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    proposals = {str(x["id"]): x for x in data.get("proposals", [])}
    if proposal_id not in proposals:
        raise ValueError("현재 검토안에 없는 ID")
    history = json.loads(DECISIONS.read_text(encoding="utf-8"))
    if any(str(x.get("id")) == proposal_id for x in history):
        raise ValueError("이미 판정한 ID")
    item = proposals[proposal_id]
    history.append({"id": proposal_id, "decision": decision, "note": note.strip()[:500],
                    "title": item["title"], "issue_key": item["issue_key"],
                    "source": item["source"], "url": item["url"],
                    "decided_at_utc": datetime.now(timezone.utc).isoformat()})
    DECISIONS.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return history[-1]

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--id", required=True)
    p.add_argument("--decision", choices=["COMPLETE", "DISCARD", "HOLD"], required=True)
    p.add_argument("--note", default="")
    args = p.parse_args()
    print(json.dumps(record(args.id, args.decision, args.note), ensure_ascii=False))
