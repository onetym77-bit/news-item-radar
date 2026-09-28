import json
import unittest
from pathlib import Path
from unittest.mock import patch

import clik_api as module


BASE = Path(__file__).resolve().parent
SOURCE = {"id": "gangnam", "name": "강남구", "clik_assembly_id": "002002"}


def list_payload(*rows):
    return {"LIST": [{"ROW": row} for row in rows], "TOTAL_COUNT": str(len(rows))}


def list_row(docid="CLIKC123456789", assembly_id="002002"):
    return {
        "DOCID": docid, "RASMBLY_ID": assembly_id, "RASMBLY_NUMPR": "9",
        "RASMBLY_SESN": "321", "MINTS_ODR": "1", "MTGNM": "본회의",
        "MTG_DE": "20260925",
    }


class ClikApiTests(unittest.TestCase):
    def test_all_25_sources_have_exact_official_assembly_ids(self):
        sources = json.loads((BASE / "sources_25.json").read_text(encoding="utf-8"))
        expected = {
            "강남구": "002002", "강동구": "002003", "강북구": "002004",
            "강서구": "002005", "관악구": "002006", "광진구": "002007",
            "구로구": "002008", "금천구": "002009", "노원구": "002010",
            "도봉구": "002011", "동대문구": "002012", "동작구": "002013",
            "마포구": "002014", "서대문구": "002015", "서초구": "002016",
            "성동구": "002017", "성북구": "002018", "송파구": "002019",
            "양천구": "002020", "영등포구": "002021", "용산구": "002022",
            "은평구": "002023", "종로구": "002024", "중구": "002025",
            "중랑구": "002026",
        }
        self.assertEqual({row["name"]: row["clik_assembly_id"] for row in sources}, expected)

    def test_list_is_bounded_deduplicated_and_uses_public_url(self):
        row = list_row()
        with patch.object(module, "fetch_payload", return_value=list_payload(row, row)) as fetch:
            records, total = module.list_minutes(SOURCE, "secret-value", 20)
        self.assertEqual(len(records), 1)
        self.assertEqual(total, 2)
        self.assertEqual(records[0]["meeting_date"], "2026-09-25")
        self.assertIn("collection=minutes", records[0]["url"])
        self.assertEqual(fetch.call_args.kwargs["listCount"], 20)
        self.assertNotIn("secret-value", str(records))

    def test_detail_rejects_cross_council_document(self):
        payload = {**list_row(), "RASMBLY_ID": "002003", "MINTS_HTML": "본문"}
        with patch.object(module, "fetch_payload", return_value=payload):
            with self.assertRaisesRegex(module.ClikAPIError, "identity mismatch"):
                module.detail_minutes(SOURCE, payload["DOCID"], "secret-value")

    def test_observation_key_matches_public_document_url_identity(self):
        row = list_row()
        with patch.object(module, "fetch_payload", return_value=list_payload(row)):
            observed = module.observation(SOURCE, "secret-value", 20)
        record = observed["records"][0]
        self.assertEqual(record["key"], module.record_key(record["url"]))
        self.assertEqual(record["document_id"], row["DOCID"])
        self.assertEqual(observed["transport"], "CLIK_OPEN_API")
        self.assertNotIn("secret-value", str(observed))

    def test_portal_staleness_requires_a_proven_later_official_meeting(self):
        portal = [{"meeting_date": "2026-09-20"}]
        newer = [{"meeting_date": "2026-09-22"}]
        same = [{"meeting_date": "2026-09-20"}]
        unknown = [{"meeting_date": ""}]
        self.assertTrue(module.portal_is_stale(portal, newer))
        self.assertFalse(module.portal_is_stale(portal, same))
        self.assertFalse(module.portal_is_stale(portal, unknown))


if __name__ == "__main__":
    unittest.main()

