import types
import unittest

from collect_l2_equal_sample import (
    SAMPLE_SIZE,
    collect,
    collect_citizen,
    common_metrics,
)
from thin_source_contract import FORBIDDEN_KEYS, load_registry, validate_thin_observation, walk_keys


class EqualL2SampleTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()
        self.sources = {row["source_id"]: row for row in self.registry["sources"]}
        self.observed_at = "2026-09-17T18:00:00+09:00"

    def citizen_module(self):
        proposals = [
            {
                "proposal_id": str(100 + index),
                "title": f"시민제안 {index}",
                "source_url": f"https://idea.seoul.go.kr/front/freeSuggest/view.do?sn={100 + index}",
                "posted_date": "2026-09-17",
            }
            for index in range(SAMPLE_SIZE)
        ]
        return types.SimpleNamespace(
            parse_list=lambda _html, limit: proposals[:limit],
            relevant_detail_text=lambda _html, title: f"{title} 본문 확인용 제한 텍스트",
        )

    def test_citizen_uses_five_detail_pages_and_persists_no_body(self):
        module = self.citizen_module()
        requested = []

        def fetcher(url):
            requested.append(url)
            return "<html>공식 화면</html>", "a" * 64

        observation = collect_citizen(
            self.sources["citizen_proposals"],
            self.observed_at,
            module=module,
            fetcher=fetcher,
        )
        self.assertEqual(len(observation["records"]), SAMPLE_SIZE)
        self.assertEqual(len(requested), SAMPLE_SIZE + 1)
        self.assertEqual(observation["diagnostics"]["detail_success"], SAMPLE_SIZE)
        self.assertEqual(validate_thin_observation(observation, self.registry), [])
        self.assertFalse(FORBIDDEN_KEYS & set(walk_keys(observation)))
        self.assertNotIn("본문 확인용", str(observation))

    def test_one_citizen_detail_failure_is_partial_not_empty(self):
        module = self.citizen_module()
        calls = 0

        def fetcher(url):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise TimeoutError("detail timeout")
            return "<html>공식 화면</html>", "b" * 64

        observation = collect_citizen(
            self.sources["citizen_proposals"],
            self.observed_at,
            module=module,
            fetcher=fetcher,
        )
        self.assertEqual(observation["access_status"], "PARTIAL")
        self.assertEqual(len(observation["records"]), SAMPLE_SIZE)
        self.assertEqual(observation["diagnostics"]["detail_failed"], 1)

    def test_common_metrics_use_the_same_denominator(self):
        module = self.citizen_module()
        observation = collect_citizen(
            self.sources["citizen_proposals"],
            self.observed_at,
            module=module,
            fetcher=lambda _url: ("<html>공식 화면</html>", "c" * 64),
        )
        metrics = common_metrics(observation)
        self.assertEqual(metrics["sample_target"], SAMPLE_SIZE)
        self.assertEqual(metrics["sample_count"], SAMPLE_SIZE)
        self.assertEqual(metrics["body_available_count"], SAMPLE_SIZE)
        self.assertEqual(metrics["title_aligned_count"], SAMPLE_SIZE)
        self.assertEqual(metrics["editorial_value_status"], "HUMAN_REVIEW_REQUIRED")

    def test_combined_collection_keeps_editorial_value_unjudged(self):
        def factory(source_id):
            source = self.sources[source_id]
            return {
                "schema": 1,
                "source_id": source_id,
                "maturity": source["maturity"],
                "collected_at_kst": self.observed_at,
                "source_url": source["official_url"],
                "access_status": "PARTIAL",
                "coverage": "FIRST_OFFICIAL_LIST_PAGE_FIRST_5_DETAILS_NO_ATTACHMENTS",
                "records": [],
                "interpretation_status": "NOT_EVALUATED",
                "diagnostics": {"detail_requested": 0},
            }

        rows = collect(
            self.registry,
            self.observed_at,
            audit_collector=lambda _source, _at: factory("seoul_audit_results"),
            citizen_collector=lambda _source, _at: factory("citizen_proposals"),
        )
        self.assertEqual([row["source_id"] for row in rows], list(("seoul_audit_results", "citizen_proposals")))
        self.assertTrue(all(row["interpretation_status"] == "NOT_EVALUATED" for row in rows))


if __name__ == "__main__":
    unittest.main()
