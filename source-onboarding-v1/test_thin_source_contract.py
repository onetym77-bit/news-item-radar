import copy
import json
import unittest
from pathlib import Path

from thin_source_contract import (
    BASE, load_registry, validate_registry, validate_thin_observation,
)

class SourceMaturityTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()

    def valid_observation(self):
        return {
            "schema": 1,
            "source_id": "citizen_proposals",
            "maturity": "L2",
            "collected_at_kst": "2026-09-16T13:00:00+09:00",
            "source_url": "https://idea.seoul.go.kr/front/allSuggest/list.do",
            "access_status": "SUCCESS",
            "coverage": "FIRST_PAGE_MAX_20",
            "interpretation_status": "NOT_EVALUATED",
            "records": [{
                "source_record_id": "202816",
                "title": "제안 제목",
                "detail_url": "https://idea.seoul.go.kr/front/freeSuggest/view.do?sn=202816",
                "published_at": "2026-09-15",
                "published_at_status": "CANDIDATE",
                "observed_at_kst": "2026-09-16T13:00:00+09:00",
                "access_status": "SUCCESS",
                "body_status": "BOUNDED_TEXT",
                "content_fingerprint": "abc123",
                "bounded_excerpt": "개인정보를 저장하지 않는 짧은 표본",
            }],
        }

    def test_current_registry_is_valid(self):
        self.assertEqual(validate_registry(self.registry, BASE.parent), [])

    def test_thin_observation_accepts_inventory_not_editorial_claims(self):
        self.assertEqual(validate_thin_observation(self.valid_observation(), self.registry), [])

    def test_l2_cannot_generate_questions_or_briefing(self):
        registry = copy.deepcopy(self.registry)
        source = next(row for row in registry["sources"] if row["source_id"] == "citizen_proposals")
        source["question_output"] = "VERIFICATION_ONLY"
        source["briefing_output"] = "HUMAN_REVIEW_QUEUE"
        errors = validate_registry(registry, BASE.parent)
        self.assertTrue(any("question_output" in error for error in errors))
        self.assertTrue(any("briefing_output" in error for error in errors))

    def test_no_source_can_write_editorial_ledger_or_raw_personal_text(self):
        for field in ("automatic_ledger_write", "raw_personal_text_persisted"):
            registry = copy.deepcopy(self.registry)
            registry["sources"][0][field] = True
            errors = validate_registry(registry, BASE.parent)
            self.assertTrue(any(field.replace("_", " ")[:4] in error or "forbidden" in error
                                for error in errors))

    def test_l4_requires_seven_day_review_and_eighty_percent_completion(self):
        registry = copy.deepcopy(self.registry)
        source = next(row for row in registry["sources"] if row["source_id"] == "construction_watch")
        source["maturity"] = "L4"
        source["evaluation"] = {"window_days": 6, "review_completion_rate": 0.79}
        errors = validate_registry(registry, BASE.parent)
        self.assertTrue(any("at least 7 days" in error for error in errors))
        self.assertTrue(any("at least 0.8" in error for error in errors))

    def test_l0_cannot_emit_records(self):
        observation = self.valid_observation()
        observation["source_id"] = "opengov_approvals"
        observation["maturity"] = "L0"
        observation["source_url"] = "https://opengov.seoul.go.kr/sanction"
        errors = validate_thin_observation(observation, self.registry)
        self.assertIn("L0 access probes cannot emit source records", errors)

    def test_failed_access_is_not_zero_new_records(self):
        observation = self.valid_observation()
        observation["access_status"] = "FAILED"
        errors = validate_thin_observation(observation, self.registry)
        self.assertIn("failed access cannot emit records", errors)

    def test_forbidden_editorial_and_personal_fields_fail_closed(self):
        for key, value in (
            ("central_question", "왜 피해가 발생했나"),
            ("victim_count", 3),
            ("raw_html", "<p>원문</p>"),
            ("author_name", "홍길동"),
        ):
            observation = self.valid_observation()
            observation["records"][0][key] = value
            errors = validate_thin_observation(observation, self.registry)
            self.assertTrue(any("forbidden" in error for error in errors), key)

    def test_duplicate_ids_and_urls_are_rejected(self):
        observation = self.valid_observation()
        observation["records"].append(copy.deepcopy(observation["records"][0]))
        errors = validate_thin_observation(observation, self.registry)
        self.assertTrue(any("duplicate source_record_id" in error for error in errors))
        self.assertTrue(any("duplicate detail_url" in error for error in errors))

    def test_verified_date_cannot_be_empty(self):
        observation = self.valid_observation()
        observation["records"][0]["published_at"] = None
        observation["records"][0]["published_at_status"] = "VERIFIED"
        errors = validate_thin_observation(observation, self.registry)
        self.assertTrue(any("verified date is empty" in error for error in errors))

    def test_thin_observation_caps_samples_at_twenty(self):
        observation = self.valid_observation()
        template = observation["records"][0]
        observation["records"] = []
        for index in range(21):
            record = copy.deepcopy(template)
            record["source_record_id"] = str(index)
            record["detail_url"] = f"https://idea.seoul.go.kr/item/{index}"
            observation["records"].append(record)
        errors = validate_thin_observation(observation, self.registry)
        self.assertTrue(any("at most 20 records" in error for error in errors))

    def test_excerpt_is_bounded(self):
        observation = self.valid_observation()
        observation["records"][0]["bounded_excerpt"] = "가" * 261
        errors = validate_thin_observation(observation, self.registry)
        self.assertTrue(any("260 characters" in error for error in errors))

if __name__ == "__main__":
    unittest.main()
