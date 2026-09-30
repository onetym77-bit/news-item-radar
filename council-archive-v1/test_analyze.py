import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE_PATH = Path(__file__).with_name("analyze.py")
SPEC = importlib.util.spec_from_file_location("council_analyze", MODULE_PATH)
analyze = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analyze)


def valid_item():
    return {
        "signal_type": "NEW_POLICY_UNCERTAINTY",
        "headline": "청년 AI 지원은 구독료보다 이용 격차를 먼저 묻는다",
        "subject": "새로 추진되는 청년 AI 지원 사업의 대상과 지원 방식이 실제 이용 장벽과 맞는지 확인한다.",
        "affected_group": "유료 AI 서비스를 이용하기 어려운 서울 청년",
        "mechanism": "수요와 장벽을 구분하지 않은 채 구독료 지원 중심으로 사업이 설계될 수 있다.",
        "civic_importance": "새 사업의 예산이 실제 접근 격차를 줄이는 방식으로 설계되는지 시민이 미리 확인할 수 있다.",
        "anchor_quote": "비용이 부담돼서 이용 못 하는 것인지 활용방법을 몰라서 접근하지 못하는 것인지 구분해야 합니다.",
        "evidence_status": "PROPOSAL",
        "unknowns": ["사업 대상", "지원 방식", "이용 장벽 조사 여부"],
        "public_question": "서울시는 비용 부담과 활용 역량 부족을 어떻게 구분해 지원 대상을 정할 것인가?",
        "counterintuitive_question": "구독료보다 실무교육과 프로젝트 지도가 실제 접근 격차를 더 줄이는 것은 아닌가?",
        "scope_hint": "CITYWIDE",
        "broadcast_potential": 78,
        "why_not_routine": "사업 시행 전 설계 단계에서 지원 방식이 실제 격차와 어긋날 가능성을 검증할 수 있다.",
    }


class AnalyzeTests(unittest.TestCase):
    def document(self):
        quote = valid_item()["anchor_quote"]
        return {
            "document_id": "CLIKC100",
            "source_id": "seoul_city",
            "source_name": "서울시의회",
            "meeting_date": "2026-09-11",
            "title": "본회의",
            "document_url": "https://example.com/minutes",
            "body": ("발언 내용입니다. " * 30) + quote + (" 추가 설명입니다." * 30),
        }

    def test_chunks_cover_full_text_in_order(self):
        text = "\n".join("문단%03d %s" % (i, "가" * 90) for i in range(120))
        pieces = analyze.chunks(text, size=1000, overlap=50)
        self.assertGreater(len(pieces), 5)
        self.assertIn("문단000", pieces[0])
        self.assertIn("문단119", pieces[-1])

    def test_new_policy_without_results_is_not_automatically_rejected(self):
        item = valid_item()
        passage = "앞 문맥. " + item["anchor_quote"] + " 뒤 문맥."
        result = analyze.validate_item(item, passage)
        self.assertEqual(result["evidence_status"], "PROPOSAL")
        self.assertEqual(result["signal_type"], "NEW_POLICY_UNCERTAINTY")

    def test_generic_question_is_rejected(self):
        item = valid_item()
        item["public_question"] = "이 사업이 시민에게 어떤 영향을 주는가?"
        with self.assertRaisesRegex(ValueError, "Generic"):
            analyze.validate_item(item, item["anchor_quote"])

    def test_analysis_resumes_and_deduplicates(self):
        document = self.document()
        state = analyze.normalize_state(None)
        with tempfile.TemporaryDirectory() as tmp:
            candidate_path = Path(tmp) / "candidates.jsonl"
            with mock.patch.object(
                analyze,
                "call_model",
                return_value={"items": [valid_item()]},
            ):
                first = analyze.analyze(
                    [document],
                    state=state,
                    candidate_path=candidate_path,
                    api_key="secret",
                    model="test-model",
                    max_calls=1,
                )
                second = analyze.analyze(
                    [document],
                    state=state,
                    candidate_path=candidate_path,
                    api_key="secret",
                    model="test-model",
                    max_calls=1,
                )
            self.assertEqual(first["new_candidate_count"], 1)
            self.assertEqual(second["new_candidate_count"], 0)
            rows = [
                json.loads(line)
                for line in candidate_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(rows), 1)
            self.assertTrue(state["documents"]["CLIKC100"]["complete"])

    def test_semantic_duplicates_are_grouped_without_losing_evidence(self):
        base = {
            "candidate_id": "one",
            "document_id": "CLIKC100",
            "source_id": "seoul_city",
            "source_name": "서울시의회",
            "meeting_date": "2026-09-11",
            "document_url": "https://example.com/minutes",
            "chunk_number": 1,
            **valid_item(),
            "review_status": "UNREVIEWED",
        }
        duplicate = {
            **base,
            "candidate_id": "two",
            "chunk_number": 2,
            "headline": "청년 AI 지원, 구독료보다 이용 장벽을 먼저 봐야 한다",
            "anchor_quote": "무료와 유료 기능의 차이보다 청년이 왜 접근하지 못하는지 먼저 확인해야 합니다.",
            "unknowns": ["수요 조사", "사업 대상"],
        }

        grouped = analyze.group_for_review([base, duplicate])

        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["related_evidence_count"], 2)
        self.assertEqual(grouped[0]["related_document_count"], 1)
        self.assertEqual(len(grouped[0]["supporting_anchors"]), 2)
        self.assertIn("수요 조사", grouped[0]["unknowns"])

    def test_different_civic_problems_remain_separate(self):
        first = {
            "candidate_id": "one",
            "document_id": "CLIKC100",
            "source_id": "seoul_city",
            "source_name": "서울시의회",
            "meeting_date": "2026-09-11",
            "document_url": "https://example.com/minutes",
            "chunk_number": 1,
            **valid_item(),
            "review_status": "UNREVIEWED",
        }
        second = {
            **first,
            "candidate_id": "other",
            "headline": "학교 통학 셔틀 비용이 학부모 부담으로 넘어갔다",
            "subject": "학교 배정과 대중교통 공백 때문에 사설 통학버스를 이용하는 가정의 비용 부담을 확인한다.",
            "affected_group": "대중교통으로 통학하기 어려운 초등학생 가정",
            "mechanism": "공공 통학 수단 부족이 사설 셔틀 비용 부담으로 전가된다.",
            "signal_type": "SERVICE_GAP",
        }

        self.assertEqual(len(analyze.group_for_review([first, second])), 2)

    def test_no_signal_marks_chunk_complete_without_candidate(self):
        document = self.document()
        state = analyze.normalize_state(None)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            analyze,
            "call_model",
            return_value={"items": []},
        ):
            payload = analyze.analyze(
                [document],
                state=state,
                candidate_path=Path(tmp) / "candidates.jsonl",
                api_key="secret",
                model="test-model",
                max_calls=1,
            )
        self.assertEqual(payload["new_candidate_count"], 0)
        self.assertTrue(state["documents"]["CLIKC100"]["complete"])


if __name__ == "__main__":
    unittest.main()
