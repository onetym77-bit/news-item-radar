import gzip
import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).with_name("archive.py")
SPEC = importlib.util.spec_from_file_location("council_archive", MODULE_PATH)
archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive)


class ArchiveTests(unittest.TestCase):
    def source(self, source_id="alpha", assembly_id="002001"):
        return {
            "id": source_id,
            "name": source_id,
            "clik_assembly_id": assembly_id,
            "list_url": "https://example.com/minutes",
        }

    def test_list_page_omits_keyword_and_paginates(self):
        calls = []

        def fake_fetch(api_key, **params):
            calls.append(params)
            return {
                "RESULT_CODE": "SUCCESS",
                "TOTAL_COUNT": "1",
                "LIST": [{"ROW": {
                    "DOCID": "CLIKC123",
                    "RASMBLY_ID": "002001",
                    "MTG_DE": "20260930",
                    "RASMBLY_NUMPR": "11",
                    "RASMBLY_SESN": "1",
                    "MTGNM": "본회의",
                    "MINTS_ODR": "1",
                }}],
            }

        with mock.patch.object(archive, "fetch_payload", fake_fetch):
            rows, total = archive.list_page(self.source(), "secret", 50, 20)

        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["docid"], "CLIKC123")
        self.assertEqual(calls[0]["startCount"], 50)
        self.assertEqual(calls[0]["searchType"], "ALL")
        self.assertNotIn("searchKeyword", calls[0])

    def test_archive_round_robin_deduplicates_and_persists_body(self):
        sources = [
            self.source("alpha", "002001"),
            self.source("beta", "002002"),
        ]
        state = archive.normalize_state(None, sources, 36)
        pages = {
            "alpha": [{"docid": "CLIKC101", "meeting_date": "2026-09-01",
                       "label": "A", "url": "https://example.com/a"}],
            "beta": [{"docid": "CLIKC202", "meeting_date": "2026-09-02",
                      "label": "B", "url": "https://example.com/b"}],
        }

        def fake_page(source, api_key, start, count):
            return (pages[source["id"]] if start == 0 else []), 1

        def fake_detail(source, item, api_key):
            return {
                "schema": 1,
                "document_id": item["docid"],
                "source_id": source["id"],
                "source_name": source["name"],
                "assembly_id": source["clik_assembly_id"],
                "meeting_date": item["meeting_date"],
                "title": item["label"],
                "document_url": item["url"],
                "official_list_url": source["list_url"],
                "body_sha256": "hash-" + item["docid"],
                "body": "본문 " * 50,
                "captured_at_kst": "2026-09-30T09:00:00+09:00",
            }

        with tempfile.TemporaryDirectory() as tmp,              mock.patch.object(archive, "list_page", fake_page),              mock.patch.object(archive, "detail_record", fake_detail):
            root = Path(tmp)
            added, errors = archive.archive(
                sources,
                api_key="secret",
                state=state,
                archive_path=root / "documents.jsonl.gz",
                new_path=root / "new.jsonl.gz",
                cutoff=date(2026, 1, 1),
                max_documents=2,
                page_size=20,
                official_dates={},
            )
            self.assertFalse(errors)
            self.assertEqual({row["source_id"] for row in added}, {"alpha", "beta"})
            self.assertEqual(len(state["documents"]), 2)
            with gzip.open(root / "documents.jsonl.gz", "rt", encoding="utf-8") as handle:
                stored = [json.loads(line) for line in handle]
            self.assertEqual(len(stored), 2)
            self.assertTrue(all(row["body"].startswith("본문") for row in stored))

            added_again, _ = archive.archive(
                sources,
                api_key="secret",
                state=state,
                archive_path=root / "documents.jsonl.gz",
                new_path=root / "new.jsonl.gz",
                cutoff=date(2026, 1, 1),
                max_documents=2,
                page_size=20,
                official_dates={},
            )
            self.assertEqual(added_again, [])
            with gzip.open(root / "documents.jsonl.gz", "rt", encoding="utf-8") as handle:
                self.assertEqual(len(list(handle)), 2)

    def test_expanded_window_reopens_source_without_losing_catalog(self):
        sources = [self.source()]
        state = archive.normalize_state(None, sources, 24)
        state["documents"]["CLIKC1"] = {"source_id": "alpha"}
        state["sources"]["alpha"]["complete"] = True
        state["sources"]["alpha"]["next_start_count"] = 500
        reopened = archive.normalize_state(state, sources, 36)
        self.assertFalse(reopened["sources"]["alpha"]["complete"])
        self.assertEqual(reopened["sources"]["alpha"]["next_start_count"], 0)
        self.assertIn("CLIKC1", reopened["documents"])

    def test_failed_source_is_not_retried_in_same_run(self):
        sources = [
            self.source("alpha", "002001"),
            self.source("beta", "002002"),
        ]
        state = archive.normalize_state(None, sources, 36)
        calls = []

        def fake_page(source, api_key, start, count):
            calls.append(source["id"])
            if source["id"] == "alpha":
                raise ValueError("temporary")
            return [], 0

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            archive,
            "list_page",
            fake_page,
        ):
            root = Path(tmp)
            _added, errors = archive.archive(
                sources,
                api_key="secret",
                state=state,
                archive_path=root / "documents.jsonl.gz",
                new_path=root / "new.jsonl.gz",
                cutoff=date(2026, 1, 1),
                max_documents=2,
                page_size=20,
                official_dates={},
            )

        self.assertEqual(calls.count("alpha"), 1)
        self.assertEqual(len(errors), 1)

    def test_run_stops_after_bounded_failed_sources(self):
        sources = [
            self.source(f"source-{index}", f"0020{index + 1:02d}")
            for index in range(6)
        ]
        state = archive.normalize_state(None, sources, 36)
        calls = []

        def fake_page(source, api_key, start, count):
            calls.append(source["id"])
            raise ValueError("temporary")

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            archive,
            "list_page",
            fake_page,
        ):
            root = Path(tmp)
            _added, errors = archive.archive(
                sources,
                api_key="secret",
                state=state,
                archive_path=root / "documents.jsonl.gz",
                new_path=root / "new.jsonl.gz",
                cutoff=date(2026, 1, 1),
                max_documents=6,
                page_size=20,
                official_dates={},
            )

        self.assertEqual(len(calls), archive.MAX_FAILED_SOURCES_PER_RUN)
        self.assertEqual(len(errors), archive.MAX_FAILED_SOURCES_PER_RUN)

    def test_official_newer_date_marks_portal_stale(self):
        sources = [self.source()]
        state = archive.normalize_state(None, sources, 36)
        state["sources"]["alpha"]["complete"] = True
        state["sources"]["alpha"]["portal_latest_date"] = "2026-08-01"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive.archive(
                sources,
                api_key="secret",
                state=state,
                archive_path=root / "documents.jsonl.gz",
                new_path=root / "new.jsonl.gz",
                cutoff=date(2026, 1, 1),
                max_documents=1,
                page_size=20,
                official_dates={"alpha": "2026-09-01"},
            )
        self.assertEqual(
            state["sources"]["alpha"]["freshness"],
            "PORTAL_STALE_USE_OFFICIAL",
        )

    def test_error_reason_redacts_credentials_and_urls(self):
        reason = archive.safe_error_reason(
            ValueError("request https://example.com/path?serviceKey=visible token=also-visible failed")
        )
        self.assertNotIn("example.com", reason)
        self.assertNotIn("visible", reason)
        self.assertNotIn("also-visible", reason)
        self.assertIn("[URL]", reason)

    def test_error_summary_groups_same_failure_across_sources(self):
        errors = [
            {
                "source_id": "alpha",
                "stage": "list",
                "error_type": "ClikAPIError",
                "reason": "CLIK API returned ERROR-301",
            },
            {
                "source_id": "beta",
                "stage": "list",
                "error_type": "ClikAPIError",
                "reason": "CLIK API returned ERROR-301",
            },
        ]
        summary = archive.error_summary(errors)
        self.assertEqual(summary[0]["count"], 2)
        self.assertEqual(summary[0]["source_count"], 2)
        self.assertEqual(summary[0]["reason"], "CLIK API returned ERROR-301")
        self.assertEqual(archive.unique_error_count(errors), 2)
        retried = [errors[0], errors[0], errors[1], errors[1]]
        self.assertEqual(archive.unique_error_count(retried), 2)

    def test_real_source_registry_covers_all_26_councils(self):
        sources = archive.load_sources(
            MODULE_PATH.parent.parent / "district-council-pilot" / "sources_25.json"
        )
        self.assertEqual(len(sources), 26)
        self.assertEqual(len({row["clik_assembly_id"] for row in sources}), 26)


if __name__ == "__main__":
    unittest.main()
