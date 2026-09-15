#!/usr/bin/env python3
"""Build a deterministic dry-run plan for the multi-agent shadow workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from contracts import AGENT_ROLES
from freeze_input import canonical_bytes, load_json, verify_snapshot

PLAN_SCHEMA_VERSION = "shadow-run-plan-v1"
OUTPUT_SCHEMA = "schemas/candidate_assessment.schema.json"
ROLE_CONTRACT = "agents/ROLE_CONTRACTS.md"
DISCOVERY_ROLES = (
    "DISCOVERY_PUBLIC",
    "DISCOVERY_CITIZEN",
    "DISCOVERY_STRUCTURE",
)
PRIMARY_LANES = ("core_discovery", "auxiliary_discovery")
RECOVERY_LANES = (
    "localization_discovery",
    "rediscovered_carryover",
    "stale_carryover",
    "freshness_holds",
    "context_holds",
    "held_for_source_detail",
)
VERIFICATION_LANES = (
    "verification_map",
    "verification_metadata_leads",
    "verification_schema_leads",
    "activity_baselines",
)
CITIZEN_SOURCE_IDS = {
    "eungdapso",
    "consumer_agency",
    "youtube",
    "youtube_signals",
    "citizen_voice",
}
STRUCTURE_SOURCE_IDS = {
    "seoul_open_data",
    "seoul_bigdata",
    "seoul_research",
    "labor_arrears",
    "consumer_price",
    "market_data",
}


def stable_record_id(row: dict) -> str:
    basis = "|".join(
        str(row.get(field, "")).strip()
        for field in ("source_id", "url", "context_subject", "text")
    )
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def role_for_source(source_id: str) -> str:
    if source_id in CITIZEN_SOURCE_IDS:
        return "DISCOVERY_CITIZEN"
    if source_id in STRUCTURE_SOURCE_IDS:
        return "DISCOVERY_STRUCTURE"
    return "DISCOVERY_PUBLIC"


def collect_refs(feed: dict, lanes: tuple[str, ...]) -> list[dict]:
    refs: dict[str, dict] = {}
    for lane in lanes:
        for row in feed.get(lane, []):
            record_id = stable_record_id(row)
            refs.setdefault(
                record_id,
                {
                    "record_id": record_id,
                    "lane": lane,
                    "source_id": str(row.get("source_id", "")),
                    "source_name": str(row.get("source_name", "")),
                    "url": str(row.get("url", "")),
                    "context_subject": str(row.get("context_subject", "")),
                },
            )
    return sorted(
        refs.values(),
        key=lambda ref: (
            ref["source_id"],
            ref["context_subject"],
            ref["record_id"],
        ),
    )


def task(
    task_id: str,
    *,
    stage: int,
    role: str,
    depends_on: list[str],
    run_if: str,
    candidate_refs: list[str],
    verification_refs: list[str],
) -> dict:
    return {
        "task_id": task_id,
        "stage": stage,
        "agent_role": role,
        "prompt_contract": ROLE_CONTRACT,
        "output_schema": OUTPUT_SCHEMA,
        "depends_on": depends_on,
        "run_if": run_if,
        "candidate_refs": candidate_refs,
        "verification_refs": verification_refs,
    }


def plan_digest(plan: dict) -> str:
    unsigned = {key: value for key, value in plan.items() if key != "run_plan_id"}
    return hashlib.sha256(canonical_bytes(unsigned)).hexdigest()


def build_run_plan(
    snapshot: dict,
    *,
    target_min: int = 2,
    target_max: int = 4,
) -> dict:
    snapshot = verify_snapshot(snapshot)
    if target_min < 1:
        raise ValueError("target_min must be at least 1")
    if target_max < target_min:
        raise ValueError("target_max must be greater than or equal to target_min")

    feed = snapshot["feed"]
    primary = collect_refs(feed, PRIMARY_LANES)
    recovery = collect_refs(feed, RECOVERY_LANES)
    verification = collect_refs(feed, VERIFICATION_LANES)
    primary_by_role = {role: [] for role in DISCOVERY_ROLES}
    for ref in primary:
        primary_by_role[role_for_source(ref["source_id"])].append(ref["record_id"])

    all_primary_ids = [ref["record_id"] for ref in primary]
    all_verification_ids = [ref["record_id"] for ref in verification]
    discovery_task_ids = [
        "discover-public",
        "discover-citizen",
        "discover-structure",
    ]
    tasks = [
        task(
            "discover-public",
            stage=1,
            role="DISCOVERY_PUBLIC",
            depends_on=[],
            run_if="always",
            candidate_refs=primary_by_role["DISCOVERY_PUBLIC"],
            verification_refs=all_verification_ids,
        ),
        task(
            "discover-citizen",
            stage=1,
            role="DISCOVERY_CITIZEN",
            depends_on=[],
            run_if="always",
            candidate_refs=primary_by_role["DISCOVERY_CITIZEN"],
            verification_refs=all_verification_ids,
        ),
        task(
            "discover-structure",
            stage=1,
            role="DISCOVERY_STRUCTURE",
            depends_on=[],
            run_if="always",
            candidate_refs=primary_by_role["DISCOVERY_STRUCTURE"],
            verification_refs=all_verification_ids,
        ),
        task(
            "editor-evaluate",
            stage=2,
            role="EDITOR",
            depends_on=discovery_task_ids,
            run_if="at_least_one_discovery_output",
            candidate_refs=all_primary_ids,
            verification_refs=all_verification_ids,
        ),
        task(
            "skeptic-challenge",
            stage=3,
            role="SKEPTIC",
            depends_on=["editor-evaluate"],
            run_if="editor_pass_or_hold",
            candidate_refs=all_primary_ids,
            verification_refs=all_verification_ids,
        ),
        task(
            "backfill-search",
            stage=4,
            role="BACKFILL",
            depends_on=["skeptic-challenge"],
            run_if=f"verified_candidate_count < {target_min}",
            candidate_refs=[ref["record_id"] for ref in recovery],
            verification_refs=all_verification_ids,
        ),
        task(
            "orchestrator-finalize",
            stage=5,
            role="ORCHESTRATOR",
            depends_on=["skeptic-challenge", "backfill-search"],
            run_if="after_required_predecessors",
            candidate_refs=all_primary_ids,
            verification_refs=all_verification_ids,
        ),
    ]
    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "mode": "DRY_RUN",
        "snapshot_id": snapshot["snapshot_id"],
        "source_run_id": snapshot.get("source_run_id", ""),
        "official_state_mutation_allowed": False,
        "model_calls_enabled": False,
        "targets": {
            "minimum_verify_today": target_min,
            "maximum_verify_today": target_max,
        },
        "pools": {
            "primary": primary,
            "recovery": recovery,
            "verification": verification,
        },
        "execution_stages": [
            {"stage": 1, "parallel": True, "tasks": discovery_task_ids},
            {"stage": 2, "parallel": False, "tasks": ["editor-evaluate"]},
            {"stage": 3, "parallel": False, "tasks": ["skeptic-challenge"]},
            {"stage": 4, "parallel": False, "tasks": ["backfill-search"]},
            {"stage": 5, "parallel": False, "tasks": ["orchestrator-finalize"]},
        ],
        "tasks": tasks,
    }
    plan["run_plan_id"] = plan_digest(plan)
    validate_run_plan(plan, expected_snapshot_id=snapshot["snapshot_id"])
    return plan


def validate_run_plan(
    plan: Any,
    *,
    expected_snapshot_id: str | None = None,
) -> dict:
    if not isinstance(plan, dict):
        raise ValueError("run plan must be a JSON object")
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise ValueError("unsupported run plan schema")
    if plan.get("mode") != "DRY_RUN" or plan.get("model_calls_enabled") is not False:
        raise ValueError("this version only permits dry-run plans")
    if plan.get("official_state_mutation_allowed") is not False:
        raise ValueError("shadow run must forbid official state mutation")
    if expected_snapshot_id and plan.get("snapshot_id") != expected_snapshot_id:
        raise ValueError("run plan does not belong to the expected snapshot")
    if plan.get("run_plan_id") != plan_digest(plan):
        raise ValueError("run_plan_id does not match plan content")

    pools = plan.get("pools")
    if not isinstance(pools, dict):
        raise ValueError("run plan pools must be an object")
    known_refs: set[str] = set()
    for pool_name in ("primary", "recovery", "verification"):
        refs = pools.get(pool_name)
        if not isinstance(refs, list):
            raise ValueError(f"pool {pool_name} must be a list")
        for ref in refs:
            record_id = ref.get("record_id") if isinstance(ref, dict) else None
            if not record_id:
                raise ValueError(f"pool {pool_name} has invalid record")
            if record_id in known_refs:
                raise ValueError(f"record appears in more than one pool: {record_id}")
            known_refs.add(record_id)

    tasks = plan.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("tasks must be a list")
    task_ids = [item.get("task_id") for item in tasks if isinstance(item, dict)]
    if len(task_ids) != len(tasks) or len(task_ids) != len(set(task_ids)):
        raise ValueError("task ids must be present and unique")
    expected_roles = set(DISCOVERY_ROLES) | {"EDITOR", "SKEPTIC", "BACKFILL", "ORCHESTRATOR"}
    actual_roles = {item.get("agent_role") for item in tasks}
    if actual_roles != expected_roles or not actual_roles <= AGENT_ROLES:
        raise ValueError("run plan must contain every required agent role exactly once")

    discovery_assignments: list[str] = []
    for item in tasks:
        if item.get("prompt_contract") != ROLE_CONTRACT:
            raise ValueError("task prompt contract mismatch")
        if item.get("output_schema") != OUTPUT_SCHEMA:
            raise ValueError("task output schema mismatch")
        unknown = [
            ref_id
            for ref_id in (
                list(item.get("candidate_refs", []))
                + list(item.get("verification_refs", []))
            )
            if ref_id not in known_refs
        ]
        if unknown:
            raise ValueError("task cites unknown record refs: " + ", ".join(unknown))
        for dependency in item.get("depends_on", []):
            if dependency not in task_ids:
                raise ValueError(f"task dependency does not exist: {dependency}")
        if item.get("agent_role") in DISCOVERY_ROLES:
            discovery_assignments.extend(item.get("candidate_refs", []))

    primary_ids = [ref["record_id"] for ref in pools["primary"]]
    if sorted(discovery_assignments) != sorted(primary_ids):
        raise ValueError("primary records must be assigned to one discovery agent each")
    if len(discovery_assignments) != len(set(discovery_assignments)):
        raise ValueError("a primary record was assigned to multiple discovery agents")

    targets = plan.get("targets", {})
    target_min = targets.get("minimum_verify_today")
    target_max = targets.get("maximum_verify_today")
    if not isinstance(target_min, int) or target_min < 1:
        raise ValueError("minimum_verify_today must be a positive integer")
    if not isinstance(target_max, int) or target_max < target_min:
        raise ValueError("maximum_verify_today must be at least the minimum")
    backfill = next(item for item in tasks if item.get("agent_role") == "BACKFILL")
    if backfill.get("run_if") != f"verified_candidate_count < {target_min}":
        raise ValueError("backfill condition does not match target minimum")
    return plan


def write_plan(path: Path, plan: dict) -> None:
    validate_run_plan(plan, expected_snapshot_id=plan.get("snapshot_id"))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    validate_run_plan(load_json(path), expected_snapshot_id=plan["snapshot_id"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target-min", type=int, default=2)
    parser.add_argument("--target-max", type=int, default=4)
    parser.add_argument("--verify", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.verify:
        plan = validate_run_plan(load_json(args.output))
    else:
        snapshot = verify_snapshot(load_json(args.snapshot))
        plan = build_run_plan(
            snapshot,
            target_min=args.target_min,
            target_max=args.target_max,
        )
        write_plan(args.output, plan)
    print(
        f"shadow plan {plan['run_plan_id']} "
        f"primary={len(plan['pools']['primary'])} "
        f"recovery={len(plan['pools']['recovery'])} "
        f"verification={len(plan['pools']['verification'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
