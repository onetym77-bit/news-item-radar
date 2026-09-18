import json
import unittest
from pathlib import Path

from validate_manual_post_links import validate

HERE = Path(__file__).resolve().parent


class ManualPostLinkTests(unittest.TestCase):
    def setUp(self):
        self.registry = json.loads((HERE / "accounts.json").read_text(encoding="utf-8"))

    def test_empty_intake_is_valid(self):
        self.assertEqual(validate({"schema": 1, "entries": []}, self.registry), [])

    def test_handle_post_must_match_registered_officeholder(self):
        data = {"schema": 1, "entries": [{
            "post_url": "https://www.facebook.com/ohsehoon4you/posts/pfbid123",
            "entity_id": "seoul",
            "officeholder_name": "오세훈",
            "observed_on": "2026-09-18",
            "review_status": "EDITOR_CONFIRMED_PUBLIC_LINK",
            "editor_note": "공개 게시물로 직접 확인",
        }]}
        self.assertEqual(validate(data, self.registry), [])

    def test_numeric_permalink_must_match_registered_id(self):
        data = {"schema": 1, "entries": [{
            "post_url": "https://www.facebook.com/permalink.php?story_fbid=12345&id=61586613525215",
            "entity_id": "yeongdeungpo",
            "officeholder_name": "조유진",
            "observed_on": "2026-09-18",
            "review_status": "EDITOR_SUBMITTED_UNREVIEWED",
            "editor_note": "",
        }]}
        self.assertEqual(validate(data, self.registry), [])

    def test_unregistered_owner_and_non_post_are_rejected(self):
        data = {"schema": 1, "entries": [{
            "post_url": "https://www.facebook.com/other/posts/12345",
            "entity_id": "seoul",
            "officeholder_name": "오세훈",
            "observed_on": "2026-09-18",
            "review_status": "EDITOR_SUBMITTED_UNREVIEWED",
            "editor_note": "",
        }]}
        errors = validate(data, self.registry)
        self.assertTrue(any("26 registered" in error for error in errors))

    def test_mismatch_and_duplicate_are_rejected(self):
        row = {
            "post_url": "https://www.facebook.com/ohsehoon4you/posts/pfbid123",
            "entity_id": "jongno",
            "officeholder_name": "유찬종",
            "observed_on": "2026-09-18",
            "review_status": "EDITOR_SUBMITTED_UNREVIEWED",
            "editor_note": "",
        }
        errors = validate({"schema": 1, "entries": [row, dict(row)]}, self.registry)
        self.assertTrue(any("does not match" in error for error in errors))
        self.assertTrue(any("duplicate" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
