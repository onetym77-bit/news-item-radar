import unittest
from unittest.mock import patch

from watch_new_minutes import compare, empty_state, record_key, render, safe_observe


def row(number):
    url = f"https://example.gov/record/main?uid={number}"
    return {"key": record_key(url), "url": url,
            "meeting_date": "2026-09-18", "label": f"제300회 본회의 {number}"}


def observed(*numbers, status="OBSERVED"):
    return {"id": "example", "name": "예시구", "status": status,
            "listed": len(numbers) if status == "OBSERVED" else None,
            "records": [row(number) for number in numbers]}


class ThinWatchRegression(unittest.TestCase):
    def test_first_observation_is_baseline_not_new(self):
        state = compare(empty_state(), [observed(3, 2, 1)], "2026-09-18T09:00:00+09:00")
        result = state["last_run"]["results"][0]
        self.assertEqual(result["status"], "BASELINE")
        self.assertIsNone(result["new_count"])
        self.assertFalse(result["candidates"])

    def test_overlapping_window_reports_only_unseen_records(self):
        first = compare(empty_state(), [observed(3, 2, 1)], "2026-09-18T09:00:00+09:00")
        second = compare(first, [observed(4, 3, 2)], "2026-09-19T09:00:00+09:00")
        result = second["last_run"]["results"][0]
        self.assertEqual(result["status"], "NEW_IN_VISIBLE_WINDOW")
        self.assertEqual(result["new_count"], 1)
        self.assertEqual(result["candidates"][0]["key"], row(4)["key"])
        self.assertEqual(second["last_run"]["briefing_output"], "NONE")

    def test_no_overlap_is_gap_not_complete_newness_claim(self):
        first = compare(empty_state(), [observed(3, 2, 1)], "2026-09-18T09:00:00+09:00")
        second = compare(first, [observed(6, 5, 4)], "2026-09-19T09:00:00+09:00")
        self.assertEqual(second["last_run"]["results"][0]["status"], "POSSIBLE_GAP")
        self.assertIn("누락 없는 수집을 보장하지 않습니다", render(second))

    def test_failure_retains_last_good_source_state(self):
        first = compare(empty_state(), [observed(3, 2, 1)], "2026-09-18T09:00:00+09:00")
        second = compare(first, [observed(status="UNKNOWN_COLLECTION")], "2026-09-19T09:00:00+09:00")
        self.assertEqual(second["sources"]["example"], first["sources"]["example"])
        result = second["last_run"]["results"][0]
        self.assertEqual(result["status"], "UNKNOWN_COLLECTION")
        self.assertIsNone(result["new_count"])

    def test_unresolved_window_does_not_erase_state(self):
        first = compare(empty_state(), [observed(3, 2, 1)], "2026-09-18T09:00:00+09:00")
        second = compare(first, [observed(status="UNKNOWN_LIST_WINDOW")], "2026-09-19T09:00:00+09:00")
        self.assertEqual(second["sources"]["example"], first["sources"]["example"])

    def test_official_alias_and_query_order_keep_identity(self):
        first = record_key("https://www.example.gov/record/main?uid=3&kind=B")
        second = record_key("https://example.gov/record/main?kind=B&uid=3")
        self.assertEqual(first, second)

    def test_one_parser_failure_is_isolated(self):
        with patch("watch_new_minutes.observe", side_effect=ValueError("bad list")):
            result = safe_observe({"id": "example", "name": "예시구"})
        self.assertEqual(result["status"], "UNKNOWN_LIST_WINDOW")
        self.assertEqual(result["records"], [])

    def test_duplicate_identity_is_rejected(self):
        with self.assertRaises(ValueError):
            compare(empty_state(), [observed(3, 3)], "2026-09-18T09:00:00+09:00")


if __name__ == "__main__":
    unittest.main()
