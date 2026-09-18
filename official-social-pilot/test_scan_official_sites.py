import json
import unittest
from pathlib import Path

from scan_official_sites import SocialLinkParser, render, social_platform
from verify_registry import validate_registry

HERE = Path(__file__).resolve().parent


class OfficialHomepageScanTests(unittest.TestCase):
    def test_all_26_homepages_have_government_directory_evidence(self):
        data = json.loads((HERE / "accounts.json").read_text(encoding="utf-8"))
        self.assertEqual(validate_registry(data), [])
        self.assertEqual(sum(bool(e["official_site"]) for e in data["entities"]), 26)
        self.assertEqual(sum(len(e["institution_accounts"]) for e in data["entities"]), 3)
        self.assertEqual(sum(len(e["officeholder_accounts"]) for e in data["entities"]), 26)

    def test_profile_links_only_not_individual_posts(self):
        self.assertEqual(social_platform("https://www.youtube.com/@district"), "youtube")
        self.assertEqual(social_platform("https://www.instagram.com/district/"), "instagram")
        self.assertIsNone(social_platform("https://www.youtube.com/watch?v=abc"))
        self.assertIsNone(social_platform("https://www.instagram.com/p/abc"))
        self.assertIsNone(social_platform("http://www.instagram.com/district"))

    def test_parser_only_returns_candidate_links(self):
        parser = SocialLinkParser("https://www.dongjak.go.kr/")
        parser.feed(
            '<a href="https://www.youtube.com/@district">채널</a>'
            '<a href="https://www.youtube.com/watch?v=abc">영상</a>'
            '<a href="/news">소식</a>'
        )
        self.assertEqual(parser.candidates, {"https://www.youtube.com/@district": "youtube"})

    def test_summary_shows_candidate_url_and_official_evidence_without_approval(self):
        result = {"sites": [{
            "entity_id": "gwanak",
            "status": "SUCCESS",
            "reason": None,
            "candidate_links": [{
                "platform": "youtube",
                "url": "https://www.youtube.com/@gwanak",
                "evidence_page": "https://www.gwanak.go.kr/",
            }],
        }]}
        summary = render(result)
        self.assertIn("https://www.youtube.com/@gwanak", summary)
        self.assertIn("https://www.gwanak.go.kr/", summary)
        self.assertIn("계정 승인 아님", summary)

    def test_missing_evidence_rejected(self):
        data = json.loads((HERE / "accounts.json").read_text(encoding="utf-8"))
        data["entities"][1]["official_site_source"] = ""
        self.assertTrue(any("evidence" in e for e in validate_registry(data)))


if __name__ == "__main__":
    unittest.main()
