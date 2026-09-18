import json
import unittest
from pathlib import Path

from search_officeholder_names import (
    discover, profile_url, queries, render, validate_seeds,
)

HERE = Path(__file__).resolve().parent


class OfficeholderNameSearchTests(unittest.TestCase):
    def setUp(self):
        self.seeds = json.loads((HERE / "name_search_seeds.json").read_text(encoding="utf-8"))
        self.registry = json.loads((HERE / "accounts.json").read_text(encoding="utf-8"))

    def test_all_26_entities_are_search_seeds_not_approved_accounts(self):
        self.assertEqual(validate_seeds(self.seeds, self.registry), [])
        self.assertEqual(len(self.seeds["entities"]), 26)
        self.assertTrue(all(e["officeholder_name"] for e in self.seeds["entities"]))

    def test_facebook_profile_url_filter_excludes_shares_and_posts(self):
        self.assertEqual(profile_url("https://m.facebook.com/example.name/?ref=search"), "https://www.facebook.com/example.name")
        self.assertEqual(profile_url("https://www.facebook.com/profile.php?id=12345"), "https://www.facebook.com/profile.php?id=12345")
        self.assertIsNone(profile_url("https://www.facebook.com/sharer.php?u=x"))
        self.assertIsNone(profile_url("https://www.facebook.com/example.name/posts/123"))
        self.assertIsNone(profile_url("https://evil.example/facebook.com/example.name"))
        self.assertIsNone(profile_url("http://www.facebook.com/example.name"))
        self.assertIsNone(profile_url("https://www.facebook.com/profile.php?id=abc"))

    def test_query_contains_name_and_municipality(self):
        row = self.seeds["entities"][0]
        self.assertIn(row["officeholder_name"], queries(row)[0])
        self.assertIn(row["municipality"], queries(row)[0])

    def test_search_success_yields_only_unverified_candidate(self):
        row = self.seeds["entities"][0]
        def fake_search(query, client_id, client_secret):
            return "SUCCESS", [
                {"link": "https://www.facebook.com/ohsehoon4you", "title": "오세훈 - Facebook"},
                {"link": "https://www.facebook.com/sharer.php?u=x", "title": "공유"},
            ]
        result = discover(row, "id", "secret", search=fake_search)
        self.assertEqual(result["status"], "SEARCHED_WITH_FACEBOOK_URLS")
        self.assertEqual(result["profile_candidates"][0]["status"], "UNVERIFIED_FACEBOOK_URL_ONLY")
        self.assertEqual(len(result["profile_candidates"]), 1)
        self.assertEqual(result["queries_attempted"], 1)

    def test_unrelated_facebook_page_is_not_a_person_candidate(self):
        row = self.seeds["entities"][0]
        result = discover(row, "id", "secret", search=lambda *args: (
            "SUCCESS", [{"link": "https://www.facebook.com/unrelated.city", "title": "시설관리공단 - Facebook"}]
        ))
        self.assertEqual(result["status"], "SEARCHED_NO_FACEBOOK_URL")
        self.assertEqual(result["profile_candidates"], [])

    def test_review_summary_lists_unverified_profile_urls(self):
        row = discover(self.seeds["entities"][0], "id", "secret", search=lambda *args: (
            "SUCCESS", [{"link": "https://www.facebook.com/ohsehoon4you", "title": "오세훈 - Facebook"}]
        ))
        summary = render({"entities": [row]})
        self.assertIn("https://www.facebook.com/ohsehoon4you", summary)
        self.assertIn("미승인 페이스북 URL", summary)
        self.assertIn("본인 계정으로 검증 완료: 0명", summary)

    def test_empty_results_and_api_error_are_distinct_from_no_account(self):
        row = self.seeds["entities"][0]
        empty = discover(row, "id", "secret", search=lambda *args: ("SUCCESS", []))
        failed = discover(row, "id", "secret", search=lambda *args: ("HTTP_403", []))
        unconfigured = discover(row, "", "")
        self.assertEqual(empty["status"], "SEARCHED_NO_FACEBOOK_URL")
        self.assertEqual(failed["status"], "HTTP_403")
        self.assertEqual(unconfigured["status"], "NOT_CONFIGURED")
        self.assertEqual(empty["queries_attempted"], 2)
        self.assertEqual(unconfigured["queries_attempted"], 0)


if __name__ == "__main__":
    unittest.main()
