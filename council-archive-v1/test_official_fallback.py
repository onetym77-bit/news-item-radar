import importlib.util
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent.parent
MODULE_PATH = ROOT / "district-council-pilot" / "collect_pilot.py"
SPEC = importlib.util.spec_from_file_location("collect_pilot_fallback", MODULE_PATH)
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


class OfficialFallbackTests(unittest.TestCase):
    def test_configured_official_entry_page_is_retried_after_timeout(self):
        primary = "https://example.com/kr/minutes/late.do"
        fallback = "https://example.com/kr/main.do"

        class FakeClient:
            calls = []

            def __init__(self, source):
                self.source = source
                self.logs = []
                self.stopped = False

            def get(self, url, form=None):
                self.calls.append(url)
                self.logs.append({"url": url, "status": 0 if url == primary else 200})
                if url == primary:
                    return None
                return pilot.Page("<html><body>공식 의회 홈페이지</body></html>")

        source = {
            "id": "retry",
            "name": "재시도",
            "list_url": primary,
            "list_fallback_url": fallback,
            "hosts": ["example.com"],
        }
        with mock.patch.object(pilot, "Client", FakeClient):
            result = pilot.run(source, date(2026, 9, 30), 1)

        self.assertEqual(FakeClient.calls, [primary, fallback])
        self.assertTrue(result["listing_ok"])
        self.assertEqual(result["effective_list_url"], fallback)

    def test_blocked_source_is_not_retried(self):
        primary = "https://example.com/kr/minutes/late.do"
        fallback = "https://example.com/kr/main.do"

        class BlockedClient:
            calls = []

            def __init__(self, source):
                self.source = source
                self.logs = []
                self.stopped = False

            def get(self, url, form=None):
                self.calls.append(url)
                self.logs.append({"url": url, "status": 403})
                self.stopped = True
                return None

        source = {
            "id": "blocked",
            "name": "차단",
            "list_url": primary,
            "list_fallback_url": fallback,
            "hosts": ["example.com"],
        }
        with mock.patch.object(pilot, "Client", BlockedClient):
            result = pilot.run(source, date(2026, 9, 30), 1)

        self.assertEqual(BlockedClient.calls, [primary])
        self.assertFalse(result["listing_ok"])


if __name__ == "__main__":
    unittest.main()
