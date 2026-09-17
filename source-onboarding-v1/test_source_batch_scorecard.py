import unittest

from source_batch_scorecard import build_scorecard, render_summary, score_observation
from thin_source_contract import load_registry


class SourceBatchScorecardTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()

    def observation(self, source_id="citizen_proposals", access="SUCCESS", count=10):
        records = []
        for index in range(count):
            records.append({
                "source_record_id": str(index),
                "title": f"표본 {index}",
                "detail_url": f"https://idea.seoul.go.kr/item/{index}",
                "published_at": "2026-09-16",
                "published_at_status": "VERIFIED",
                "observed_at_kst": "2026-09-17T10:00:00+09:00",
                "access_status": "SUCCESS",
                "body_status": "BOUNDED_TEXT",
                "content_fingerprint": f"fp-{index}",
            })
        source = next(row for row in self.registry["sources"] if row["source_id"] == source_id)
        return {
            "schema": 1,
            "source_id": source_id,
            "maturity": source["maturity"],
            "collected_at_kst": "2026-09-17T10:00:00+09:00",
            "source_url": source["official_url"],
            "access_status": access,
            "coverage": "BOUNDED_MAX_20",
            "records": records,
            "interpretation_status": "NOT_EVALUATED",
            "diagnostics": {
                "candidate_count": count,
                "unresolved_detail_url_count": 0,
            },
        }

    def reviews(self, source_id, labels):
        return [
            {
                "source_id": source_id,
                "source_record_id": str(index),
                "label": label,
                "reviewed_on": "2026-09-17",
                "note": "",
            }
            for index, label in enumerate(labels)
        ]

    def test_failed_access_remains_unknown_not_zero_value(self):
        observation = self.observation(count=0, access="FAILED")
        row = score_observation(observation, self.registry, [])
        self.assertEqual(row["content_availability"], "UNKNOWN_DUE_TO_ACCESS_FAILURE")
        self.assertEqual(row["technical_gate"], "RETRY_ACCESS")
        self.assertIsNone(row["candidate_count"])
        self.assertIsNone(row["body_available_rate"])
        self.assertEqual(row["editorial_gate"], "NOT_EVALUATED")

    def test_one_failed_source_does_not_abort_other_sources(self):
        failed = self.observation(count=0, access="FAILED")
        valid = self.observation(source_id="seoul_audit_results", count=10)
        result = build_scorecard([failed, valid], self.registry, [])
        self.assertEqual(len(result["sources"]), 2)
        self.assertEqual(result["sources"][0]["technical_gate"], "RETRY_ACCESS")
        self.assertNotEqual(result["sources"][1]["technical_gate"], "INVALID_OBSERVATION")

    def test_l1_probe_of_higher_maturity_source_uses_observed_depth(self):
        observation = self.observation(source_id="seoul_audit_results", count=10)
        for record in observation["records"]:
            record["body_status"] = "NOT_FETCHED"
        row = score_observation(observation, self.registry, [])
        self.assertEqual(row["technical_gate"], "READY_FOR_L2_SAMPLE")
        self.assertEqual(row["editorial_gate"], "NOT_READY_FOR_EDITORIAL_REVIEW")

    def test_l1_listing_cannot_receive_editorial_value_judgment(self):
        observation = self.observation(source_id="district_councils_25", count=10)
        observation["source_url"] = "https://example.go.kr/list"
        for record in observation["records"]:
            record["body_status"] = "NOT_FETCHED"
        labels = ["PROMISING"] * 10
        row = score_observation(
            observation,
            self.registry,
            self.reviews("district_councils_25", labels),
        )
        self.assertEqual(row["technical_gate"], "READY_FOR_L2_SAMPLE")
        self.assertIsNone(row["body_available_rate"])
        self.assertIsNone(row["record_access_rate"])
        self.assertEqual(row["editorial_gate"], "NOT_READY_FOR_EDITORIAL_REVIEW")

    def test_wide_screening_rejects_more_than_twenty_records(self):
        row = score_observation(self.observation(count=21), self.registry, [])
        self.assertEqual(row["technical_gate"], "INVALID_OBSERVATION")
        self.assertIn("exceeds 20", " ".join(row["errors"]))

    def test_access_only_probe_uses_readiness_not_empty_listing(self):
        source = next(row for row in self.registry["sources"] if row["source_id"] == "district_councils_25")
        observation = {
            "schema": 1,
            "source_id": source["source_id"],
            "maturity": source["maturity"],
            "collected_at_kst": "2026-09-17T10:00:00+09:00",
            "source_url": "https://example.go.kr/list",
            "access_status": "PARTIAL",
            "coverage": "ACCESS_ONLY_25_COUNCIL_LISTS",
            "records": [],
            "interpretation_status": "NOT_EVALUATED",
            "technical_readiness": "GROUP_ACCESS_REVIEW",
            "diagnostics": {"council_total": 25, "council_access_success": 20},
        }
        row = score_observation(observation, self.registry, [])
        self.assertEqual(row["technical_gate"], "REVIEW_GROUP_ACCESS")
        self.assertEqual(row["editorial_gate"], "NOT_READY_FOR_EDITORIAL_REVIEW")

    def test_summary_exposes_group_access_counts(self):
        source = next(row for row in self.registry["sources"] if row["source_id"] == "district_councils_25")
        observation = {
            "schema": 1, "source_id": source["source_id"], "maturity": source["maturity"],
            "collected_at_kst": "2026-09-17T10:00:00+09:00",
            "source_url": "https://example.go.kr/list", "access_status": "PARTIAL",
            "coverage": "ACCESS_ONLY_25_COUNCIL_LISTS", "records": [],
            "interpretation_status": "NOT_EVALUATED", "technical_readiness": "GROUP_ACCESS_REVIEW",
            "diagnostics": {
                "council_total": 25, "council_access_success": 20,
                "council_access_partial": 2, "council_access_failed": 3,
            },
        }
        summary = render_summary(build_scorecard([observation], self.registry, []))
        self.assertIn("성공 20 · 부분 2 · 실패 3", summary)

    def test_no_human_labels_means_no_editorial_value_judgment(self):
        row = score_observation(self.observation(), self.registry, [])
        self.assertEqual(row["editorial_gate"], "NOT_EVALUATED")

    def test_incomplete_review_cannot_recommend_deepening(self):
        reviews = self.reviews("citizen_proposals", ["PROMISING"] * 7)
        row = score_observation(self.observation(), self.registry, reviews)
        self.assertEqual(row["editorial_gate"], "INSUFFICIENT_REVIEW")

    def test_sufficient_useful_sample_can_only_propose_deepening(self):
        labels = ["PROMISING"] * 4 + ["VERIFY"] * 2 + ["NOISE"] * 4
        row = score_observation(
            self.observation(),
            self.registry,
            self.reviews("citizen_proposals", labels),
        )
        self.assertEqual(row["editorial_gate"], "DEEPEN_CANDIDATE")
        self.assertFalse(build_scorecard(
            [self.observation()],
            self.registry,
            self.reviews("citizen_proposals", labels),
        )["automatic_maturity_transition"])

    def test_duplicate_source_observation_is_isolated(self):
        observation = self.observation()
        result = build_scorecard([observation, observation], self.registry, [])
        self.assertEqual(result["sources"][1]["technical_gate"], "INVALID_OBSERVATION")
        self.assertIn("duplicate", result["sources"][1]["errors"][0])

    def test_scorecard_never_emits_questions_or_briefing(self):
        result = build_scorecard([self.observation()], self.registry, [])
        self.assertEqual(result["question_output"], "NONE")
        self.assertEqual(result["briefing_output"], "NONE")
        self.assertNotIn("central_question", str(result))


if __name__ == "__main__":
    unittest.main()
