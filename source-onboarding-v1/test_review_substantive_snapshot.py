import csv
import json
import tempfile
import unittest
from pathlib import Path

from review_substantive_snapshot import evaluate, load_snapshot, render


class FrozenReviewTests(unittest.TestCase):
    def setUp(self):
        self.cards = []
        for source_id, host in (
            ("seoul_audit_results", "news.seoul.go.kr"),
            ("citizen_proposals", "idea.seoul.go.kr"),
        ):
            for number in range(3):
                self.cards.append({
                    "source_id": source_id,
                    "source_record_id": f"{source_id}-{number}",
                    "title": f"검토 문서 {number}",
                    "detail_url": f"https://{host}/record/{number}",
                    "body_status": "READABLE_CLAIM",
                    "review_excerpt": "짧은 검토 문장",
                    "raw_body_persisted": False,
                    "human_label": None,
                })
        self.snapshot = {
            "schema": 1,
            "trial": "SUBSTANTIVE_BODY_SOURCE_COMPARISON",
            "sample_size_per_source": 3,
            "collected_at_kst": "2026-09-17T18:00:00+09:00",
            "question_output": "NONE",
            "briefing_output": "NONE",
            "automatic_ledger_write": False,
            "cards": self.cards,
        }

    def write_reviews(self, path, labels):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["source_id", "source_record_id", "label", "reviewed_on", "note"]
            )
            writer.writeheader()
            for card, label in zip(self.cards, labels):
                writer.writerow({
                    "source_id": card["source_id"],
                    "source_record_id": card["source_record_id"],
                    "label": label,
                    "reviewed_on": "2026-09-18" if label else "",
                    "note": "",
                })

    def test_partial_labels_do_not_produce_source_winner(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot_path = root / "comparison.json"
            snapshot_path.write_text(json.dumps(self.snapshot, ensure_ascii=False), encoding="utf-8")
            reviews_path = root / "reviews.csv"
            self.write_reviews(reviews_path, ["PROMISING", "", "", "", "", ""])
            snapshot, digest = load_snapshot(snapshot_path)
            result = evaluate(snapshot, digest, reviews_path)
            self.assertEqual(result["human_review_count"], 1)
            self.assertEqual(result["interpretation_status"], "HUMAN_REVIEW_INCOMPLETE")
            self.assertIsNone(result["source_winner"])
            self.assertIn("3건씩의 비율로 우수 소스", render(result))

    def test_completed_tiny_sample_is_descriptive_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reviews_path = root / "reviews.csv"
            self.write_reviews(reviews_path, ["PROMISING", "VERIFY", "NOISE"] * 2)
            result = evaluate(self.snapshot, "a" * 64, reviews_path)
            self.assertEqual(result["interpretation_status"], "PILOT_DESCRIPTIVE_ONLY")
            self.assertIsNone(result["source_winner"])
            self.assertEqual(result["metrics"][0]["reviewed_count"], 3)

    def test_raw_body_in_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "comparison.json"
            self.snapshot["cards"][0]["raw_body_persisted"] = True
            path.write_text(json.dumps(self.snapshot, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_snapshot(path)

    def test_labeled_unknown_record_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "reviews.csv"
            path.write_text(
                "source_id,source_record_id,label,reviewed_on,note\n"
                "citizen_proposals,not-in-snapshot,PROMISING,2026-09-18,\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                evaluate(self.snapshot, "a" * 64, path)


if __name__ == "__main__":
    unittest.main()
