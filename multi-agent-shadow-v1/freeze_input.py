#!/usr/bin/env python3
"""Freeze one collected feed for fair control-versus-shadow comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "multi-agent-shadow-input-v1"
CANDIDATE_LANES = (
    "core_discovery",
    "auxiliary_discovery",
    "localization_discovery",
    "rediscovered_carryover",
    "stale_carryover",
    "archived_stale",
    "freshness_holds",
    "context_holds",
    "activity_baselines",
    "verification_metadata_leads",
    "verification_schema_leads",
    "verification_map",
    "held_for_source_detail",
)
REQUIRED_FEED_KEYS = ("generated_at_kst", "status", "funnel", "metrics", *CANDIDATE_LANES)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def validate_feed(feed: Any) -> dict:
    if not isinstance(feed, dict):
        raise ValueError("daily feed must be a JSON object")
    missing = [key for key in REQUIRED_FEED_KEYS if key not in feed]
    if missing:
        raise ValueError("daily feed is missing keys: " + ", ".join(missing))
    if not isinstance(feed["funnel"], dict):
        raise ValueError("daily feed funnel must be an object")
    if not isinstance(feed["metrics"], list):
        raise ValueError("daily feed metrics must be a list")
    for lane in CANDIDATE_LANES:
        if not isinstance(feed[lane], list):
            raise ValueError(f"daily feed lane {lane} must be a list")
        if any(not isinstance(row, dict) for row in feed[lane]):
            raise ValueError(f"daily feed lane {lane} contains a non-object row")
    return feed


def feed_digest(feed: dict) -> str:
    return hashlib.sha256(canonical_bytes(feed)).hexdigest()


def candidate_counts(feed: dict) -> dict[str, int]:
    return {lane: len(feed[lane]) for lane in CANDIDATE_LANES}


def build_snapshot(feed: dict, *, run_id: str = "", code_sha: str = "") -> dict:
    feed = validate_feed(feed)
    digest = feed_digest(feed)
    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": digest,
        "source_feed_sha256": digest,
        "source_generated_at_kst": str(feed["generated_at_kst"]),
        "source_run_id": str(run_id),
        "source_code_sha": str(code_sha),
        "contract": {
            "same_input_required": True,
            "read_only": True,
            "official_state_mutation_allowed": False,
            "candidate_lanes": list(CANDIDATE_LANES),
        },
        "counts": {
            "source_metrics": len(feed["metrics"]),
            "candidates_by_lane": candidate_counts(feed),
        },
        "feed": feed,
    }


def verify_snapshot(snapshot: Any) -> dict:
    if not isinstance(snapshot, dict):
        raise ValueError("shadow snapshot must be a JSON object")
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported shadow snapshot schema")
    feed = validate_feed(snapshot.get("feed"))
    digest = feed_digest(feed)
    if snapshot.get("snapshot_id") != digest:
        raise ValueError("snapshot_id does not match embedded feed")
    if snapshot.get("source_feed_sha256") != digest:
        raise ValueError("source_feed_sha256 does not match embedded feed")
    expected_counts = candidate_counts(feed)
    actual_counts = snapshot.get("counts", {}).get("candidates_by_lane")
    if actual_counts != expected_counts:
        raise ValueError("candidate counts do not match embedded feed")
    contract = snapshot.get("contract", {})
    if contract.get("official_state_mutation_allowed") is not False:
        raise ValueError("shadow input must forbid official state mutation")
    return snapshot


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_snapshot(path: Path, snapshot: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    verify_snapshot(load_json(path))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--code-sha", default="")
    parser.add_argument("--verify", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.verify:
        snapshot = verify_snapshot(load_json(args.output))
        print(
            f"verified shadow input {snapshot['snapshot_id']} "
            f"from run {snapshot.get('source_run_id', '')}"
        )
        return 0
    if args.feed is None:
        raise SystemExit("--feed is required unless --verify is used")
    snapshot = build_snapshot(
        load_json(args.feed),
        run_id=args.run_id,
        code_sha=args.code_sha,
    )
    write_snapshot(args.output, snapshot)
    print(
        f"froze shadow input {snapshot['snapshot_id']} "
        f"with {sum(snapshot['counts']['candidates_by_lane'].values())} rows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
