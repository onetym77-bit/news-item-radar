import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "editorial_pipeline_head_contract", Path(__file__).with_name("pipeline.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def record(item_id="one", issue="청사 재정 선택"):
    return {
        "id": item_id,
        "family": "서울시의회",
        "source": "서울시의회 회의록",
        "headline": issue,
        "url": "https://example.org/" + item_id,
        "evidence_text": "사업비와 시설 규모를 함께 조정하는 방안을 검토하고 있습니다.",
        "context": "사업비 증가와 시설 축소 사이에서 주민 편익과 재정 선택을 함께 확인해야 합니다.",
        "date": "2026-09-22",
        "claim_status": "의원 발언·미검증",
        "issue_hint": issue,
    }


class HeadContractTests(unittest.TestCase):
    def test_input_contract_holds_title_only_record(self):
        bad = {**record(), "evidence_text": "짧음", "context": ""}
        valid, holds = module.validate_source_records([bad])
        self.assertEqual(valid, [])
        self.assertEqual(holds[0]["reason"], "본문 근거 부족")

    def test_cluster_uses_exact_issue_not_shared_meeting_url(self):
        first = record("one", "청사 재정 선택")
        second = {**record("two", "청소년 쉼터 공백"), "url": first["url"]}
        chosen, holds, audit = module.cluster_source_records([first, second])
        self.assertEqual(len(chosen), 2)
        self.assertEqual(holds, [])
        self.assertFalse(audit["fuzzy_merge"])

    def test_cluster_removes_exact_same_issue(self):
        first = record("one", "청사 재정 선택")
        second = record("two", "청사 재정 선택")
        chosen, holds, audit = module.cluster_source_records([first, second])
        self.assertEqual([item["id"] for item in chosen], ["one"])
        self.assertEqual(holds[0]["representative_id"], "one")
        self.assertEqual(audit["exact_duplicates"], 1)

    def test_persisted_shadow_queue_respects_human_decisions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            specs = (
                ("district-council-pilot/output/recent-l3", "district"),
                ("citizen-proposal-pilot/output", "citizen"),
                ("interest-radar-v2/output", "youtube"),
            )
            for directory, item_id in specs:
                path = root / directory
                path.mkdir(parents=True)
                (path / "editorial_review_queue.json").write_text(
                    json.dumps({"schema": 1, "items": [{
                        "id": item_id, "title": item_id,
                        "family": "25개 자치구의회" if item_id == "district" else "",
                    }]}, ensure_ascii=False), encoding="utf-8")
                (path / "editorial_review_decisions.json").write_text(
                    json.dumps([{"id": item_id, "decision": "DISCARD"}]
                               if item_id == "citizen" else [], ensure_ascii=False),
                    encoding="utf-8")
            with patch.object(module, "ROOT", root):
                bundle = module.load_shadow_review_queues()
        self.assertEqual([item["id"] for item in bundle["items"]], ["district", "youtube"])
        self.assertTrue(all(item["production_eligible"] is False for item in bundle["items"]))
        self.assertTrue(all(item["briefing_output"] == "NONE" for item in bundle["items"]))

    def test_head_run_can_finish_with_only_shadow_review(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            queue_dir = root / "district-council-pilot/output/recent-l3"
            queue_dir.mkdir(parents=True)
            (queue_dir / "editorial_review_queue.json").write_text(
                json.dumps({"schema": 1, "items": [{
                    "id": "district", "title": "구청사 재정 선택",
                    "family": "25개 자치구의회",
                }]}, ensure_ascii=False), encoding="utf-8")
            output = root / "latest.json"
            with patch.object(module, "ROOT", root):
                result = module.run("test", output_path=output)
        self.assertEqual(result["status"], "SHADOW_REVIEW_READY")
        self.assertEqual(result["proposals"], [])
        self.assertEqual([item["id"] for item in result["shadow_reviews"]], ["district"])
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(result["head_contract_version"], "1.0")

    def test_coverage_keeps_production_and_shadow_counts_separate(self):
        bundle = {"queues": [{"source": "25개 자치구의회", "pending": 2}]}
        coverage = module.build_source_coverage(
            [record()], [record()], [record()], [], bundle, [])
        by_source = {row["source"]: row for row in coverage}
        self.assertEqual(by_source["서울시의회"]["model_input"], 1)
        self.assertEqual(by_source["25개 자치구의회"]["pending_shadow"], 2)
        self.assertEqual(by_source["25개 자치구의회"]["state"], "그림자 사람 판정 대기")


if __name__ == "__main__":
    unittest.main()
