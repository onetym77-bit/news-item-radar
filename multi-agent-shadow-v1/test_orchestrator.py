#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "shadow_orchestrator",
    HERE / "orchestrator.py",
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load orchestrator.py")
orchestrator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(orchestrator)

FREEZE_SPEC = importlib.util.spec_from_file_location(
    "shadow_freeze_for_orchestrator",
    HERE / "freeze_input.py",
)
if FREEZE_SPEC is None or FREEZE_SPEC.loader is None:
    raise RuntimeError("cannot load freeze_input.py")
freeze = importlib.util.module_from_spec(FREEZE_SPEC)
FREEZE_SPEC.loader.exec_module(freeze)


def row(source_id: str, text: str, suffix: str) -> dict:
    return {
        "source_id": source_id,
        "source_name": source_id,
        "text": text,
        "url": f"https://example.test/{suffix}",
        "context_subject": text[:20],
    }


def snapshot() -> dict:
    feed = {
        "generated_at_kst": "2026-09-15T09:30:00+09:00",
        "status": "OK",
        "funnel": {},
        "metrics": [],
    }
    for lane in freeze.CANDIDATE_LANES:
        feed[lane] = []
    feed["core_discovery"] = [
        row("council_minutes", "서울 시내버스 임금 부담", "public"),
        row("eungdapso", "서울 시민의 반복 민원", "citizen"),
        row("seoul_open_data", "서울 지원 실적 격차", "structure"),
    ]
    feed["context_holds"] = [
        row("council_minutes", "적용 범위 확인 대기", "hold"),
    ]
    feed["verification_schema_leads"] = [
        row("seoul_bigdata", "검증할 데이터 구조", "verify"),
    ]
    return freeze.build_snapshot(feed, run_id="run-1", code_sha="abc")


class OrchestratorTests(unittest.TestCase):
    def test_plan_contains_all_roles_and_no_model_calls(self):
        plan = orchestrator.build_run_plan(snapshot())
        roles = {task["agent_role"] for task in plan["tasks"]}
        self.assertEqual(
            roles,
            set(orchestrator.DISCOVERY_ROLES)
            | {"EDITOR", "SKEPTIC", "BACKFILL", "ORCHESTRATOR"},
        )
        self.assertFalse(plan["model_calls_enabled"])
        self.assertFalse(plan["official_state_mutation_allowed"])

    def test_primary_candidates_are_partitioned_once(self):
        plan = orchestrator.build_run_plan(snapshot())
        assignments = []
        by_role = {}
        for task in plan["tasks"]:
            if task["agent_role"] in orchestrator.DISCOVERY_ROLES:
                by_role[task["agent_role"]] = task["candidate_refs"]
                assignments.extend(task["candidate_refs"])
        primary = [ref["record_id"] for ref in plan["pools"]["primary"]]
        self.assertCountEqual(assignments, primary)
        self.assertEqual(len(assignments), len(set(assignments)))
        self.assertEqual(len(by_role["DISCOVERY_PUBLIC"]), 1)
        self.assertEqual(len(by_role["DISCOVERY_CITIZEN"]), 1)
        self.assertEqual(len(by_role["DISCOVERY_STRUCTURE"]), 1)

    def test_backfill_is_conditional_and_uses_recovery_pool(self):
        plan = orchestrator.build_run_plan(snapshot(), target_min=3, target_max=4)
        backfill = next(
            task for task in plan["tasks"]
            if task["agent_role"] == "BACKFILL"
        )
        self.assertEqual(backfill["run_if"], "verified_candidate_count < 3")
        self.assertEqual(
            backfill["candidate_refs"],
            [ref["record_id"] for ref in plan["pools"]["recovery"]],
        )

    def test_overlapping_row_is_assigned_to_highest_priority_pool_once(self):
        source = snapshot()
        duplicate = row("seoul_bigdata", "동일 후보 중복 노출", "duplicate")
        source["feed"]["core_discovery"].append(duplicate)
        source["feed"]["context_holds"].append(dict(duplicate))
        source["feed"]["verification_map"].append(dict(duplicate))
        unsigned = {key: value for key, value in source.items() if key != "snapshot_id"}
        source["snapshot_id"] = freeze.snapshot_digest(unsigned)

        plan = orchestrator.build_run_plan(source)
        duplicate_id = orchestrator.stable_record_id(duplicate)
        memberships = [
            pool_name
            for pool_name, refs in plan["pools"].items()
            if duplicate_id in {ref["record_id"] for ref in refs}
        ]
        self.assertEqual(memberships, ["primary"])

    def test_same_snapshot_produces_stable_plan(self):
        first = orchestrator.build_run_plan(snapshot())
        second = orchestrator.build_run_plan(snapshot())
        self.assertEqual(first["run_plan_id"], second["run_plan_id"])

    def test_unknown_record_reference_is_rejected(self):
        plan = orchestrator.build_run_plan(snapshot())
        plan["tasks"][0]["candidate_refs"].append("missing-record")
        plan["run_plan_id"] = orchestrator.plan_digest(plan)
        with self.assertRaisesRegex(ValueError, "unknown record"):
            orchestrator.validate_run_plan(plan)

    def test_invalid_target_range_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "target_max"):
            orchestrator.build_run_plan(snapshot(), target_min=4, target_max=2)

    def test_written_plan_round_trips(self):
        plan = orchestrator.build_run_plan(snapshot())
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "plan.json"
            orchestrator.write_plan(target, plan)
            loaded = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(loaded["run_plan_id"], plan["run_plan_id"])
        orchestrator.validate_run_plan(
            loaded,
            expected_snapshot_id=snapshot()["snapshot_id"],
        )


if __name__ == "__main__":
    unittest.main()
