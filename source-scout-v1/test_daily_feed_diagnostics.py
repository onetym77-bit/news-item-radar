#!/usr/bin/env python3
"""Tests for truthful qualified-to-new source diagnostics."""
import unittest

from collect_daily_feed import (
    pending_review_window_open,
    qualification_paths,
    source_revision_for_row,
)


def row(suffix, freshness_status):
    return {
        "source_id": "council_minutes",
        "url": f"https://example.test/{suffix}",
        "text": f"원자료 {suffix}",
        "qualified": True,
        "freshness_status": freshness_status,
    }


class QualificationPathTests(unittest.TestCase):
    def test_nine_qualified_rows_partition_into_three_repeats_and_six_old(self):
        records = (
            [row(f"repeat-{index}", "FRESH") for index in range(3)]
            + [row(f"stale-{index}", "STALE_CARRYOVER") for index in range(5)]
            + [row("archived", "ARCHIVED_STALE")]
        )
        prior = {source_revision_for_row(item) for item in records[:3]}
        result = qualification_paths(
            records, prior,
            [{"source_id": "council_minutes", "http_ok": True}],
        )
        self.assertEqual(
            {key: result[key] for key in (
                "qualified", "fresh_new", "fresh_repeat", "stale",
                "archived", "date_hold"
            )},
            {
                "qualified": 9, "fresh_new": 0, "fresh_repeat": 3,
                "stale": 5, "archived": 1, "date_hold": 0,
            },
        )
        self.assertEqual(result["zero_new_reason"], "NO_NEW_FRESH_QUALIFIED")
        self.assertEqual(
            sum(result[key] for key in (
                "fresh_new", "fresh_repeat", "stale", "archived", "date_hold"
            )),
            result["qualified"],
        )

    def test_new_row_and_fetch_failure_are_reported_separately(self):
        records = [row("new", "FRESH"), {**row("not-qualified", "FRESH"), "qualified": False}]
        result = qualification_paths(
            records, set(),
            [{"source_id": "consumer_agency", "http_ok": False, "error": "SSL failure"}],
        )
        self.assertEqual(result["fresh_new"], 1)
        self.assertEqual(result["qualified"], 1)
        self.assertEqual(result["failed_sources"][0]["source_id"], "consumer_agency")
        self.assertEqual(result["zero_new_reason"], "")


class ReviewWindowTests(unittest.TestCase):
    def test_unreviewed_core_card_remains_open_for_seven_days(self):
        row = {
            "first_seen": "2026-09-15",
            "lane": "CORE_DISCOVERY",
            "editor_judgment": "",
            "review_eligible": "false",
        }
        self.assertTrue(pending_review_window_open(row, "2026-09-17"))
        self.assertTrue(pending_review_window_open(row, "2026-09-21"))
        self.assertFalse(pending_review_window_open(row, "2026-09-22"))

    def test_reviewed_and_non_discovery_cards_do_not_reopen(self):
        base = {"first_seen": "2026-09-15", "lane": "CORE_DISCOVERY"}
        self.assertFalse(pending_review_window_open(
            {**base, "editor_judgment": "VERIFY"}, "2026-09-17"
        ))
        self.assertFalse(pending_review_window_open(
            {**base, "lane": "LOCALIZE_TO_SEOUL"}, "2026-09-17"
        ))
        self.assertFalse(pending_review_window_open(
            {**base, "first_seen": "invalid"}, "2026-09-17"
        ))


if __name__ == "__main__":
    unittest.main()
