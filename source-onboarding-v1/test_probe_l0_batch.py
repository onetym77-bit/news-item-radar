import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import Request

from probe_l0_batch import (
    MAX_RESPONSE_BYTES,
    PageSignalParser,
    SafeRedirectHandler,
    TARGET_IDS,
    build_observation,
    fetch_url,
    render_summary,
)
from thin_source_contract import load_registry, validate_thin_observation


class FakeHeaders:
    def __init__(self, content_type="text/html", charset="utf-8"):
        self.content_type = content_type
        self.charset = charset

    def get_content_type(self):
        return self.content_type

    def get_content_charset(self):
        return self.charset


class FakeResponse:
    def __init__(self, body: bytes, url: str, status=200, content_type="text/html"):
        self.body = body
        self.url = url
        self.status = status
        self.headers = FakeHeaders(content_type)
        self.read_size = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def getcode(self):
        return self.status

    def geturl(self):
        return self.url

    def read(self, size=-1):
        self.read_size = size
        return self.body if size < 0 else self.body[:size]


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.timeout = None

    def open(self, request, timeout):
        self.timeout = timeout
        return self.response


class L0BatchProbeTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()
        self.sources = {row["source_id"]: row for row in self.registry["sources"]}

    def test_parser_ignores_script_style_and_counts_only_same_host_https_links(self):
        html = """
        <html><head><title>공식 목록</title><style>비밀 2026-09-16</style></head>
        <body><script>숨김 2026-09-15</script><ul><li>
        <a href="/one">내부</a><a href="http://example.com/two">비보안</a>
        <a href="https://other.example/three">외부</a>공개 2026-09-14
        </li></ul></body></html>
        """
        parser = PageSignalParser("https://example.com/list")
        parser.feed(html)
        self.assertEqual(parser.title, "공식 목록")
        self.assertNotIn("비밀", parser.visible_text)
        self.assertNotIn("숨김", parser.visible_text)
        self.assertEqual(parser.internal_link_count, 1)
        self.assertEqual(parser.article_like_node_count, 1)

    def test_redirect_handler_blocks_cross_host_and_downgrade(self):
        handler = SafeRedirectHandler("example.com")
        request = Request("https://example.com/start")
        for target in ("https://evil.example/path", "http://example.com/path"):
            with self.assertRaises(ValueError):
                handler.redirect_request(request, None, 302, "Found", {}, target)

    def test_response_is_bounded_and_raw_content_is_not_returned(self):
        body = (
            b"<html><head><title>List</title></head><body>"
            + b"<a href='/x'>x</a><li>2026-09-16 visible</li>"
            + b"A" * (MAX_RESPONSE_BYTES + 100)
            + b"</body></html>"
        )
        response = FakeResponse(body, "https://example.com/list")
        status, diagnostics = fetch_url(
            "https://example.com/list",
            max_bytes=MAX_RESPONSE_BYTES,
            opener=FakeOpener(response),
        )
        self.assertEqual(status, "PARTIAL")
        self.assertEqual(response.read_size, MAX_RESPONSE_BYTES + 1)
        self.assertEqual(diagnostics["response_bytes"], MAX_RESPONSE_BYTES)
        self.assertTrue(diagnostics["response_truncated"])
        serialized = json.dumps(diagnostics, ensure_ascii=False)
        self.assertNotIn("<html>", serialized)
        self.assertNotIn("visible", serialized)

    def test_l0_observations_never_emit_records_and_validate(self):
        for source_id in TARGET_IDS:
            source = dict(self.sources[source_id])
            if not source.get("official_url"):
                source["official_url"] = "https://example.com/list"
            observation = build_observation(
                source,
                collected_at="2026-09-16T15:00:00+09:00",
                fetcher=lambda _url: (
                    "SUCCESS",
                    {
                        "http_status": 200,
                        "error_code": None,
                        "response_bytes": 1200,
                        "response_truncated": False,
                        "content_type": "text/html",
                        "content_sha256": "abc",
                        "page_title": "공식 목록",
                        "visible_text_chars": 500,
                        "internal_link_count": 10,
                        "article_like_node_count": 4,
                        "date_like_token_count": 3,
                        "redirect_count": 0,
                    },
                ),
            )
            self.assertEqual(observation["records"], [])
            self.assertEqual(observation["interpretation_status"], "NOT_EVALUATED")
            self.assertEqual(validate_thin_observation(observation, self.registry), [])

    def test_failed_access_is_explicit_and_not_zero_records(self):
        source = self.sources["opengov_approvals"]
        observation = build_observation(
            source,
            collected_at="2026-09-16T15:00:00+09:00",
            fetcher=lambda _url: (
                "FAILED",
                {
                    "http_status": 429,
                    "error_code": "HTTP_429",
                    "response_bytes": 0,
                    "response_truncated": False,
                    "content_type": None,
                    "content_sha256": None,
                    "page_title": None,
                    "visible_text_chars": 0,
                    "internal_link_count": 0,
                    "article_like_node_count": 0,
                    "date_like_token_count": 0,
                    "redirect_count": 0,
                },
            ),
        )
        self.assertEqual(observation["access_status"], "FAILED")
        self.assertEqual(observation["records"], [])
        self.assertEqual(observation["technical_readiness"], "KEEP_L0")
        self.assertNotIn("0건", render_summary([observation]))

    def test_non_html_response_is_partial_without_body(self):
        response = FakeResponse(
            b"%PDF secret contents",
            "https://example.com/list",
            content_type="application/pdf",
        )
        status, diagnostics = fetch_url(
            "https://example.com/list",
            opener=FakeOpener(response),
        )
        self.assertEqual(status, "PARTIAL")
        self.assertEqual(diagnostics["error_code"], "NON_HTML_RESPONSE")
        self.assertIsNone(diagnostics["page_title"])


if __name__ == "__main__":
    unittest.main()
