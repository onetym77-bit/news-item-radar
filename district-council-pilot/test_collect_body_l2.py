import unittest
from datetime import date

import collect_body_l2 as module


SOURCE = {"id": "sample", "name": "표본구의회"}
ROW = {
    "url": "https://example.org/meeting/1", "meeting_date": "2026-09-21",
    "body_ok": True, "body_characters": 2100, "speech_turns": 5,
    "body_sha256": "a" * 64, "metadata_check": "MATCH",
    "date_crosschecked": True, "identity_conflict": False,
    "provisional": False, "diagnosis": "BODY_OK",
    "review_windows": [{"passage": "저장하면 안 되는 원문 발언"}],
}
RESULT = {"listing_ok": True, "selected": [ROW], "requests": [{}, {}]}


class BodyL2Tests(unittest.TestCase):
    def test_matched_body_preserves_metadata_not_speech(self):
        row = module.summarize(SOURCE, RESULT)
        self.assertEqual(row["status"], "BODY_METADATA_MATCH")
        self.assertEqual(row["speech_turns"], 5)
        self.assertEqual(row["review_window_count"], 1)
        self.assertNotIn("passage", row)
        self.assertNotIn("저장하면 안 되는", str(row))
        self.assertIsNone(row["public_release_date"])

    def test_unverified_and_conflicting_metadata_do_not_pass(self):
        unverified = module.summarize(SOURCE, {**RESULT, "selected": [{**ROW, "metadata_check": "UNVERIFIED"}]})
        conflict = module.summarize(SOURCE, {**RESULT, "selected": [{**ROW, "metadata_check": "CONFLICT"}]})
        self.assertEqual(unverified["status"], "METADATA_UNVERIFIED")
        self.assertEqual(conflict["status"], "METADATA_CONFLICT")

    def test_provisional_body_is_separate(self):
        row = module.summarize(SOURCE, {**RESULT, "selected": [{**ROW, "provisional": True}]})
        self.assertEqual(row["status"], "PROVISIONAL_BODY")

    def test_collection_failure_is_not_zero_items(self):
        row = module.summarize(SOURCE, {"listing_ok": False, "selected": [], "diagnosis": "LIST_FETCH_FAILED"})
        self.assertEqual(row["status"], "UNKNOWN_COLLECTION")
        self.assertFalse(row["body_observed"])

    def test_future_meeting_is_not_ready(self):
        row = module.summarize(SOURCE, {**RESULT, "selected": [{**ROW, "diagnosis": "FUTURE_MEETING"}]})
        self.assertEqual(row["status"], "FUTURE_MEETING")

    def test_full_denominator_required(self):
        with self.assertRaisesRegex(ValueError, "25 distinct"):
            module.collect([SOURCE], date(2026, 9, 22))


if __name__ == "__main__":
    unittest.main()
