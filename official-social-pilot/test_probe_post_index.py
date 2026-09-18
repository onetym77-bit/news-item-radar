import json
import unittest
from pathlib import Path

from probe_post_index import account_identity, probe, query_for, render, strict_post_url
from verify_registry import validate_registry

HERE = Path(__file__).resolve().parent


class PostIndexFeasibilityTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((HERE / "accounts.json").read_text(encoding="utf-8"))
        self.assertEqual(validate_registry(self.data), [])

    def test_all_26_accounts_are_editor_registered(self):
        self.assertEqual(len(self.data["entities"]), 26)
        self.assertTrue(all(
            len(entity["officeholder_accounts"]) == 1
            and entity["officeholder_accounts"][0]["verification_kind"] == "EDITOR_ATTESTED"
            for entity in self.data["entities"]
        ))

    def test_handle_post_must_match_registered_account(self):
        account = "https://www.facebook.com/ohsehoon4you"
        self.assertEqual(
            strict_post_url("https://m.facebook.com/ohsehoon4you/posts/pfbid123?ref=search", account),
            "https://www.facebook.com/ohsehoon4you/posts/pfbid123",
        )
        self.assertIsNone(strict_post_url("https://www.facebook.com/other/posts/pfbid123", account))
        self.assertIsNone(strict_post_url("https://www.facebook.com/ohsehoon4you", account))
        self.assertIsNone(strict_post_url("https://www.facebook.com/ohsehoon4you/posts", account))
        self.assertIsNone(strict_post_url("http://www.facebook.com/ohsehoon4you/posts/pfbid123", account))

    def test_numeric_profile_id_kept_for_permalink(self):
        account = "https://www.facebook.com/profile.php?id=61586613525215"
        self.assertEqual(account_identity(account), ("numeric", "61586613525215"))
        self.assertEqual(
            strict_post_url("https://www.facebook.com/permalink.php?story_fbid=12345&id=61586613525215", account),
            "https://www.facebook.com/permalink.php?story_fbid=12345&id=61586613525215",
        )
        self.assertIsNone(strict_post_url(
            "https://www.facebook.com/permalink.php?story_fbid=12345&id=100000660477712", account
        ))
        self.assertIn("61586613525215", query_for(account, "조유진"))

    def test_search_result_is_only_url_candidate_not_verified_post(self):
        entity = next(e for e in self.data["entities"] if e["id"] == "seoul")

        def fake_search(*args):
            return "SUCCESS", [
                {"link": "https://www.facebook.com/other/posts/123", "description": "ignored"},
                {"link": "https://www.facebook.com/ohsehoon4you/posts/pfbid123", "description": "ignored"},
                {"link": "https://www.facebook.com/ohsehoon4you/posts/pfbid123?ref=x"},
            ]

        row = probe(entity, "id", "secret", search=fake_search)
        self.assertEqual(row["status"], "INDEX_URL_CANDIDATES")
        self.assertEqual(row["strict_owner_url_candidates"], [
            "https://www.facebook.com/ohsehoon4you/posts/pfbid123"
        ])
        self.assertFalse(row["platform_checked"])
        self.assertEqual(row["date_status"], "NOT_AVAILABLE_IN_SEARCH_INDEX")
        summary = render({"entities": [row]})
        self.assertIn("L1 통과: 아님", summary)

    def test_absence_and_access_failure_are_distinct(self):
        entity = self.data["entities"][0]
        empty = probe(entity, "id", "secret", search=lambda *args: ("SUCCESS", []))
        error = probe(entity, "id", "secret", search=lambda *args: ("HTTP_429", []))
        not_configured = probe(entity, "", "")
        self.assertEqual(empty["status"], "SEARCHED_NO_STRICT_URL")
        self.assertEqual(error["status"], "HTTP_429")
        self.assertEqual(not_configured["status"], "NOT_CONFIGURED")


if __name__ == "__main__":
    unittest.main()
