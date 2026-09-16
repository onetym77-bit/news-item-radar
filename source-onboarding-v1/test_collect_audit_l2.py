import unittest

from collect_audit_l2 import (
    MAX_DETAIL_RECORDS,
    collect_one,
    derive_detail_record,
)
from collect_l1_batch import record
from thin_source_contract import FORBIDDEN_KEYS, load_registry, validate_thin_observation, walk_keys


LISTING_HTML = """
<html><body><main>
<h3><a href="/gov/archives/580648">아동양육시설 등 관리운영 실태 특정감사 결과 공개문</a></h3>
<p>등록일 : 2026-09-04</p>
</main></body></html>
"""

DETAIL_HTML = """
<html><head>
<meta property="og:title" content="아동양육시설 등 관리운영 실태 특정감사 결과 공개문">
</head><body>
<h3>감사계획 및 결과</h3>
<h2>아동양육시설 등 관리운영 실태 특정감사 결과 공개문</h2>
<div>담당부서 감사위원회 감사담당관</div>
<div>문의 02-2133-1891</div>
<div>수정일 2026-09-03</div>
<section>
<h3>1. 감사배경 및 목적</h3>
<h3>2. 감사개요</h3>
<p>감사대상 : 여성가족실</p>
<p>기간·범위 : 2026.03.23. ~ 2026.04.17.</p>
<h3>3. 감사 중점사항</h3>
<a href="/files/public-result.pdf">붙임 공개문</a>
</section>
<div>추천하기0</div>
<div>페이지 만족도 평가</div>
</body></html>
"""


def diagnostics(page: str) -> dict:
    return {
        "error_code": None,
        "http_status": 200,
        "response_bytes": len(page.encode("utf-8")),
        "content_sha256": "a" * 64,
        "redirect_count": 0,
    }


class AuditL2Tests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()
        self.source = next(
            row for row in self.registry["sources"] if row["source_id"] == "seoul_audit_results"
        )
        self.observed_at = "2026-09-16T18:00:00+09:00"
        self.listing_record = record(
            "580648",
            "아동양육시설 등 관리운영 실태 특정감사 결과 공개문",
            "https://news.seoul.go.kr/gov/archives/580648",
            "2026-09-04",
            "VERIFIED",
            self.observed_at,
        )

    def test_exact_title_and_modified_date_do_not_replace_listing_date(self):
        row = derive_detail_record(self.listing_record, DETAIL_HTML, diagnostics(DETAIL_HTML))
        self.assertEqual(row["title_match"], "EXACT")
        self.assertEqual(row["published_at"], "2026-09-04")
        self.assertEqual(row["detail_published_at"], None)
        self.assertEqual(row["detail_modified_at"], "2026-09-03")
        self.assertEqual(row["detail_date_kind"], "MODIFIED_ONLY")
        self.assertEqual(row["listing_detail_date_match"], "NOT_COMPARABLE")
        self.assertEqual(row["body_status"], "STRUCTURED")

    def test_only_derived_structure_is_persisted(self):
        row = derive_detail_record(self.listing_record, DETAIL_HTML, diagnostics(DETAIL_HTML))
        self.assertGreater(row["structural_markers"]["audit_background"], 0)
        self.assertGreater(row["structural_markers"]["audit_subject"], 0)
        self.assertGreater(row["structural_markers"]["audit_period_scope"], 0)
        self.assertEqual(row["attachment_link_count_not_fetched"], 1)
        serialized = str(row)
        self.assertNotIn("02-2133-1891", serialized)
        self.assertNotIn("감사위원회 감사담당관", serialized)
        self.assertFalse(FORBIDDEN_KEYS & set(walk_keys(row)))

    def test_collection_is_bounded_to_five_details(self):
        listing = "<html><body>" + "".join(
            f'<h3><a href="/gov/archives/{580600 + i}">감사 결과 공개문 {i}</a></h3>'
            f'<p>등록일 : 2026-09-{10 - i:02d}</p>'
            for i in range(7)
        ) + "</body></html>"
        requested = []

        def detail_fetcher(url):
            requested.append(url)
            title = f"감사 결과 공개문 {int(url.rsplit('/', 1)[-1]) - 580600}"
            page = DETAIL_HTML.replace(
                "아동양육시설 등 관리운영 실태 특정감사 결과 공개문", title
            )
            return "SUCCESS", page, diagnostics(page)

        observation = collect_one(
            self.source,
            self.observed_at,
            listing_fetcher=lambda _url: ("SUCCESS", listing, diagnostics(listing)),
            detail_fetcher=detail_fetcher,
        )
        self.assertEqual(len(requested), MAX_DETAIL_RECORDS)
        self.assertEqual(len(observation["records"]), MAX_DETAIL_RECORDS)
        self.assertEqual(observation["diagnostics"]["attachment_downloads"], 0)

    def test_one_detail_failure_is_partial_not_zero_records(self):
        observation = collect_one(
            self.source,
            self.observed_at,
            listing_fetcher=lambda _url: ("SUCCESS", LISTING_HTML, diagnostics(LISTING_HTML)),
            detail_fetcher=lambda _url: (
                "FAILED",
                None,
                {"error_code": "NETWORK_ERROR", "http_status": None},
            ),
        )
        self.assertEqual(observation["access_status"], "PARTIAL")
        self.assertEqual(len(observation["records"]), 1)
        self.assertEqual(observation["records"][0]["body_status"], "FAILED")
        self.assertEqual(observation["records"][0]["detail_error_code"], "NETWORK_ERROR")

    def test_l2_observation_satisfies_fail_closed_contract(self):
        observation = collect_one(
            self.source,
            self.observed_at,
            listing_fetcher=lambda _url: ("SUCCESS", LISTING_HTML, diagnostics(LISTING_HTML)),
            detail_fetcher=lambda _url: ("SUCCESS", DETAIL_HTML, diagnostics(DETAIL_HTML)),
        )
        self.assertEqual(validate_thin_observation(observation, self.registry), [])
        self.assertEqual(observation["interpretation_status"], "NOT_EVALUATED")
        self.assertFalse(FORBIDDEN_KEYS & set(walk_keys(observation)))

    def test_mismatched_title_is_held_partial(self):
        page = DETAIL_HTML.replace(
            "아동양육시설 등 관리운영 실태 특정감사 결과 공개문",
            "전혀 다른 감사 문서",
        )
        row = derive_detail_record(self.listing_record, page, diagnostics(page))
        self.assertEqual(row["title_match"], "MISMATCH")
        self.assertEqual(row["access_status"], "PARTIAL")


if __name__ == "__main__":
    unittest.main()
