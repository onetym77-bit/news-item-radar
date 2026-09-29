import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/district-council-recent-l3.yml"


class DistrictWorkflowContractTests(unittest.TestCase):
    def test_review_and_persistence_expect_same_shadow_schema(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        review_section = workflow.split(
            "- name: Check editorial shadow boundary", 1
        )[1].split("- name: Upload bounded recent L3 report", 1)[0]
        persist_section = workflow.split(
            "- name: Validate and place deduplication history", 1
        )[1].split(
            "- name: Persist identity history and redacted editorial queue only", 1
        )[0]

        expected = 'assert data["schema"] == 2'
        persisted = 'assert shadow["schema"] == 2'
        self.assertIn(expected, review_section)
        self.assertIn(persisted, persist_section)
        self.assertNotIn('assert shadow["schema"] == 1', persist_section)
        self.assertIn('assert shadow["proposals"] == []', persist_section)


if __name__ == "__main__":
    unittest.main()
