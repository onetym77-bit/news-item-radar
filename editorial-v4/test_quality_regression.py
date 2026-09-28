import importlib.util
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "quality_regression", HERE / "evaluate_quality_regression.py"
)
QUALITY = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(QUALITY)


class QualityRegressionTests(unittest.TestCase):
    def test_all_fixed_cases_pass(self):
        report = QUALITY.evaluate()
        self.assertGreaterEqual(report["case_count"], 6)
        self.assertEqual(report["failed"], [])

    def test_required_editorial_failures_are_locked(self):
        report = QUALITY.evaluate()
        case_ids = {row["id"] for row in report["results"]}
        self.assertTrue(
            {
                "promotion-is-not-incident",
                "new-program-without-history",
                "local-facility-expansion",
                "budget-is-not-failure",
                "future-event-is-not-current",
                "construction-keyword-context",
            }.issubset(case_ids)
        )


if __name__ == "__main__":
    unittest.main()
