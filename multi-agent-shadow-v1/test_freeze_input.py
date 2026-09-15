#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "shadow_freeze_input",
    HERE / "freeze_input.py",
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load freeze_input.py")
freeze = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(freeze)


def sample_feed() -> dict:
    feed = {
        "generated_at_kst": "2026-09-15T09:30:00+09:00",
        "status": "OK",
        "funnel": {"extracted": 2, "selected_discovery": 1},
        "metrics": [{"id": "council_minutes", "status": 200}],
    }
    for lane in freeze.CANDIDATE_LANES:
        feed[lane] = []
    feed["core_discovery"] = [
        {
            "source_id": "council_minutes",
            "context_subject": "서울 시내버스 통상임금·노사 분쟁",
            "text": "현재 미지급 통상임금은 약 2,900억 원입니다.",
            "url": "https://example.test/minutes/1",
        }
    ]
    return feed


class FreezeInputTests(unittest.TestCase):
    def test_identical_feed_has_identical_snapshot_id(self):
        first = freeze.build_snapshot(sample_feed(), run_id="one", code_sha="a")
        second = freeze.build_snapshot(sample_feed(), run_id="two", code_sha="b")
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])

    def test_feed_change_changes_snapshot_id(self):
        first_feed = sample_feed()
        second_feed = sample_feed()
        second_feed["core_discovery"][0]["text"] += " 지연이자도 증가합니다."
        self.assertNotEqual(
            freeze.build_snapshot(first_feed)["snapshot_id"],
            freeze.build_snapshot(second_feed)["snapshot_id"],
        )

    def test_tampered_snapshot_is_rejected(self):
        snapshot = freeze.build_snapshot(sample_feed())
        snapshot["feed"]["core_discovery"][0]["text"] = "변조된 문장"
        with self.assertRaisesRegex(ValueError, "snapshot_id"):
            freeze.verify_snapshot(snapshot)

    def test_snapshot_forbids_official_state_mutation(self):
        snapshot = freeze.build_snapshot(sample_feed())
        self.assertFalse(snapshot["contract"]["official_state_mutation_allowed"])
        freeze.verify_snapshot(snapshot)

    def test_written_snapshot_round_trips(self):
        snapshot = freeze.build_snapshot(
            sample_feed(),
            run_id="34908347462",
            code_sha="abc123",
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "shadow_input.json"
            freeze.write_snapshot(target, snapshot)
            loaded = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(loaded["source_run_id"], "34908347462")
        self.assertEqual(loaded["source_code_sha"], "abc123")
        self.assertEqual(
            loaded["counts"]["candidates_by_lane"]["core_discovery"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
