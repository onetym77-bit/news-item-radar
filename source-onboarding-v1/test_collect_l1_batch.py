import unittest

from collect_l1_batch import (
    MAX_RECORDS,
    collect_one,
    parse_audit,
    parse_environment,
)
from thin_source_contract import load_registry, validate_thin_observation


AUDIT_HTML = """
<html><body>
<main>
<h3><a href="/gov/archives/580648?listPage=1">아동양육시설 관리운영 특정감사 결과</a></h3>
<p>등록일 : 2026-09-04</p>
<h3><a href="/gov/archives/580600">두 번째 감사 결과</a></h3>
<p>등록일 : 2026-08-07</p>
</main>
</body></html>
"""

ENV_DIRECT_HTML = """
<html><body>
<h2>공고/공람</h2>
<ul>
<li><a href="/eims/usr/notice/view.do?seq=101">첫 번째 환경영향평가 공람</a> 2026-09-11</li>
<li><a href="/eims/usr/notice/view.do?seq=102">두 번째 환경영향평가 공람</a> 2026-09-10</li>
</ul>
<h2>자료실</h2>
<a href="/eims/usr/data/view.do?seq=999">수집 제외 자료</a> 2026-09-09
</body></html>
"""

ENV_SCRIPT_HTML = """
<html><body>
<h2>공고/공람</h2>
<ul><li><a href="#" onclick="goPublicNotice('1234567890123')">상세주소 미해결 공람</a> 2026-09-11</li></ul>
<h2>자료실</h2>
</body></html>
"""


class L1ListingTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()
        self.sources = {row["source_id"]: row for row in self.registry["sources"]}
        self.observed_at = "2026-09-16T16:00:00+09:00"

    def test_audit_extracts_unique_id_title_date_and_detail_url(self):
        rows, diagnostics = parse_audit(
            AUDIT_HTML,
            "https://news.seoul.go.kr/gov/archives/category/test",
            self.observed_at,
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["source_record_id"], "580648")
        self.assertEqual(rows[0]["published_at"], "2026-09-04")
        self.assertEqual(rows[0]["published_at_status"], "VERIFIED")
        self.assertEqual(rows[0]["body_status"], "NOT_FETCHED")
        self.assertEqual(diagnostics["date_missing_count"], 0)

    def test_environment_collects_only_public_notice_section_with_safe_links(self):
        rows, diagnostics = parse_environment(
            ENV_DIRECT_HTML,
            "https://eims.seoul.go.kr/eims/usr/main/index.do?tr_code=rsite",
            self.observed_at,
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["source_record_id"], "101")
        self.assertEqual(rows[0]["published_at_status"], "CANDIDATE")
        self.assertTrue(all("/notice/view.do" in row["detail_url"] for row in rows))
        self.assertEqual(diagnostics["unresolved_detail_url_count"], 0)

    def test_unresolved_script_link_is_held_not_fabricated(self):
        rows, diagnostics = parse_environment(
            ENV_SCRIPT_HTML,
            "https://eims.seoul.go.kr/eims/usr/main/index.do?tr_code=rsite",
            self.observed_at,
        )
        self.assertEqual(rows, [])
        self.assertEqual(diagnostics["candidate_count"], 1)
        self.assertEqual(diagnostics["unresolved_detail_url_count"], 1)
        self.assertEqual(diagnostics["unresolved_link_shapes"], ["goPublicNotice:13"])

    def test_listing_is_bounded_to_twenty_records(self):
        items = "".join(
            f'<li><a href="/eims/usr/notice/view.do?seq={i}">공람 항목 {i}</a> 2026-09-01</li>'
            for i in range(100, 130)
        )
        rows, _ = parse_environment(
            f"<h2>공고/공람</h2><ul>{items}</ul><h2>자료실</h2>",
            "https://eims.seoul.go.kr/eims/usr/main/index.do?tr_code=rsite",
            self.observed_at,
        )
        self.assertEqual(len(rows), MAX_RECORDS)

    def test_l1_observations_validate_and_do_not_contain_editorial_fields(self):
        fixtures = {
            "seoul_audit_results": AUDIT_HTML,
        }
        for source_id, page in fixtures.items():
            source = self.sources[source_id]
            observation = collect_one(
                source,
                self.observed_at,
                fetcher=lambda _url, page=page: (
                    "SUCCESS",
                    page,
                    {
                        "error_code": None,
                        "http_status": 200,
                        "response_bytes": len(page.encode("utf-8")),
                        "content_sha256": "abc",
                        "redirect_count": 0,
                    },
                ),
            )
            self.assertEqual(validate_thin_observation(observation, self.registry), [])
            self.assertNotIn("central_question", str(observation))
            self.assertNotIn("full_body", str(observation))
            self.assertLessEqual(len(observation["records"]), MAX_RECORDS)


if __name__ == "__main__":
    unittest.main()
