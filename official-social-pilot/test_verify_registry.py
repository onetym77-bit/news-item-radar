import json
import unittest
from pathlib import Path

from verify_registry import DIRECTORY, canonical, evaluate, validate_registry

HERE = Path(__file__).resolve().parent


class OfficialSocialRegistryTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((HERE / "accounts.json").read_text(encoding="utf-8"))

    def test_registry_has_26_distinct_entities_and_safe_verified_links(self):
        self.assertEqual(validate_registry(self.data), [])
        self.assertEqual(len(self.data["entities"]), 26)
        self.assertEqual(sum(len(e["officeholder_accounts"]) for e in self.data["entities"]), 26)

    def test_official_directory_link_is_confirmed_without_fetching_social_profiles(self):
        html = '<a href="https://www.youtube.com/user/seoullive">서울시</a>'
        result = evaluate(self.data, "SUCCESS", html)
        youtube = next(a for a in result["accounts"] if a["platform"] == "youtube")
        instagram = next(a for a in result["accounts"] if a["platform"] == "instagram")
        self.assertEqual(youtube["status"], "CONFIRMED_LISTED")
        self.assertEqual(instagram["status"], "NOT_LISTED_NEEDS_REVIEW")
        self.assertEqual(result["posts_collected"], 0)
        self.assertFalse(result["briefing_connected"])

    def test_access_failure_does_not_claim_account_absence(self):
        result = evaluate(self.data, "SOURCE_UNAVAILABLE", None)
        self.assertEqual(sum(a["status"] == "SOURCE_UNAVAILABLE" for a in result["accounts"]), 3)
        self.assertEqual(sum(a["status"] == "EDITOR_ATTESTED_NOT_PLATFORM_RECHECKED" for a in result["accounts"]), 26)
        self.assertEqual(len(result["entities_without_registered_accounts"]), 0)

    def test_search_result_cannot_be_registered_as_official_evidence(self):
        bad = json.loads(json.dumps(self.data))
        bad["entities"][0]["institution_accounts"][0]["verification_kind"] = "SEARCH_RESULT"
        self.assertTrue(validate_registry(bad))

    def test_editor_roster_mismatch_rejected(self):
        bad = json.loads(json.dumps(self.data))
        bad["entities"][0]["officeholder_accounts"][0]["officeholder_name"] = "다른 이름"
        self.assertTrue(any("editor roster" in e for e in validate_registry(bad)))

    def test_numeric_facebook_profile_ids_are_distinct(self):
        urls = [
            account["url"]
            for entity in self.data["entities"]
            for account in entity["officeholder_accounts"]
            if "/profile.php" in account["url"]
        ]
        self.assertEqual(len(urls), 2)
        self.assertEqual(len({canonical(url) for url in urls}), 2)

    def test_duplicate_account_rejected(self):
        bad = json.loads(json.dumps(self.data))
        bad["entities"][0]["institution_accounts"].append(
            dict(bad["entities"][0]["institution_accounts"][0])
        )
        self.assertTrue(any("duplicate" in e for e in validate_registry(bad)))


if __name__ == "__main__":
    unittest.main()
