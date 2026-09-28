import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class V4UiContractTests(unittest.TestCase):
    def test_integrated_shadow_panel_and_decision_controls_exist(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="editorialV4Shadow"', html)
        self.assertIn("shadow_reviews", script)
        self.assertIn("data-copy-id", script)
        self.assertIn("review-editorial-v4.yml", script)

    def test_ui_explains_static_decision_boundary(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("판정 ID 복사", html)
        self.assertIn("GitHub Actions", html)


if __name__ == "__main__":
    unittest.main()
