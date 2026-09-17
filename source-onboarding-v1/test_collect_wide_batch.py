import unittest

from collect_wide_batch import collect, collect_citizen, probe_district, probe_environment_l1_readiness
from thin_source_contract import load_registry, validate_thin_observation


class WideBatchTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()
        self.sources = {row["source_id"]: row for row in self.registry["sources"]}
        self.observed_at = "2026-09-17T17:00:00+09:00"

    def test_citizen_listing_adapter_emits_no_body_or_editorial_fields(self):
        proposals = [{
            "proposal_id": "101",
            "title": "시민제안 표본",
            "source_url": "https://idea.seoul.go.kr/front/freeSuggest/view.do?sn=101",
            "posted_date": "2026-09-17",
        }]
        row = collect_citizen(
            self.sources["citizen_proposals"],
            self.observed_at,
            fetcher=lambda _url: ("<html></html>", "pagehash"),
            parser=lambda _html, limit: proposals[:limit],
        )
        self.assertEqual(validate_thin_observation(row, self.registry), [])
        self.assertEqual(row["records"][0]["body_status"], "NOT_FETCHED")
        self.assertNotIn("central_question", str(row))
        self.assertNotIn("bounded_excerpt", str(row))

    def test_environment_unresolved_links_are_not_fabricated_as_records(self):
        html = """
        <h2>공고/공람</h2>
        <a href="#" onclick="goNews('1234567890123')">환경평가 공람</a> 2026-09-17
        <h2>자료실</h2>
        """
        row = probe_environment_l1_readiness(
            self.sources["environment_assessment"],
            self.observed_at,
            fetcher=lambda _url: (
                "SUCCESS", html, {"error_code": None, "http_status": 200}
            ),
        )
        self.assertEqual(row["records"], [])
        self.assertEqual(row["technical_readiness"], "L1_ADAPTER_REVIEW")
        self.assertEqual(row["diagnostics"]["unresolved_detail_url_count"], 1)
        self.assertEqual(validate_thin_observation(row, self.registry), [])

    def test_district_probe_is_access_only_for_all_twenty_five(self):
        source_set = [
            {"id": f"d{i}", "list_url": f"https://council{i}.go.kr/list"}
            for i in range(25)
        ]
        def fetcher(url, timeout=8):
            index = int(url.split("council", 1)[1].split(".", 1)[0])
            if index == 24:
                return "FAILED", {"error_code": "TIMEOUT"}
            return "SUCCESS", {"error_code": None}
        row = probe_district(
            self.sources["district_councils_25"],
            self.observed_at,
            fetcher=fetcher,
            source_set=source_set,
        )
        self.assertEqual(row["access_status"], "PARTIAL")
        self.assertEqual(row["records"], [])
        self.assertEqual(row["diagnostics"]["council_total"], 25)
        self.assertEqual(row["diagnostics"]["council_access_success"], 24)
        self.assertEqual(row["diagnostics"]["council_access_failed"], 1)
        self.assertIn("d24:TIMEOUT", row["diagnostics"]["council_failure_summary"])
        self.assertEqual(validate_thin_observation(row, self.registry), [])

    def test_one_source_failure_does_not_abort_the_batch(self):
        def access(source, collected_at):
            return {
                "schema": 1, "source_id": source["source_id"], "maturity": source["maturity"],
                "collected_at_kst": collected_at, "source_url": source["official_url"],
                "access_status": "SUCCESS", "coverage": "ACCESS_ONLY_NO_RECORDS",
                "records": [], "interpretation_status": "NOT_EVALUATED",
                "technical_readiness": "READY_FOR_L1_REVIEW", "diagnostics": {},
            }
        def audit(_source, _observed_at):
            raise RuntimeError("isolated failure")
        def citizen(source, collected_at):
            return {
                "schema": 1, "source_id": source["source_id"], "maturity": source["maturity"],
                "collected_at_kst": collected_at, "source_url": source["official_url"],
                "access_status": "PARTIAL", "coverage": "FIRST_OFFICIAL_LIST_PAGE_MAX_20",
                "records": [], "interpretation_status": "NOT_EVALUATED",
                "diagnostics": {"candidate_count": None},
            }
        def district(source, collected_at):
            return {
                "schema": 1, "source_id": source["source_id"], "maturity": source["maturity"],
                "collected_at_kst": collected_at, "source_url": "https://example.go.kr/list",
                "access_status": "PARTIAL", "coverage": "ACCESS_ONLY_25_COUNCIL_LISTS",
                "records": [], "interpretation_status": "NOT_EVALUATED",
                "technical_readiness": "GROUP_ACCESS_REVIEW", "diagnostics": {},
            }
        rows = collect(
            self.registry, self.observed_at,
            access_probe=access, environment_probe=lambda source, observed_at: access(source, observed_at), audit_collector=audit,
            citizen_collector=citizen, district_probe=district,
        )
        self.assertEqual(len(rows), 5)
        audit_row = next(row for row in rows if row["source_id"] == "seoul_audit_results")
        self.assertEqual(audit_row["access_status"], "FAILED")
        self.assertTrue(any(row["access_status"] == "SUCCESS" for row in rows))

    def test_batch_scope_does_not_include_construction_without_detail_urls(self):
        self.assertNotIn("construction_watch", __import__("collect_wide_batch").TARGET_IDS)


if __name__ == "__main__":
    unittest.main()
