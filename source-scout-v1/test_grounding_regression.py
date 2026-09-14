import importlib.util
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


scout = load_module("source_scout_grounding_regression", "scout_sources.py")
feed = load_module("source_feed_grounding_regression", "collect_daily_feed.py")


class GroundingRegressionTests(unittest.TestCase):
    def setUp(self):
        self.council = {
            "id": "council_minutes",
            "name": "서울시의회 회의록",
            "local": True,
            "voice": False,
            "role": "BOTH",
        }
        self.research = {
            "id": "seoul_research",
            "name": "서울연구원",
            "local": True,
            "voice": False,
            "role": "BOTH",
        }
        self.labor = {
            "id": "labor_arrears",
            "name": "임금체불",
            "local": False,
            "voice": False,
            "role": "BOTH",
        }
        self.open_data = {
            "id": "seoul_open_data",
            "name": "열린데이터",
            "local": True,
            "voice": False,
            "role": "VERIFICATION",
        }

    def signals(self, text, source=None, kind="PAGE_CHUNK"):
        return scout.score_text(text, source or self.council, kind)[3]

    def test_generic_speech_is_rejected(self):
        result = self.signals(
            "서울의 교육격차를 줄이고 안전한 학교를 만들기 위해 최선을 다하겠습니다"
        )
        self.assertEqual(result["precheck_status"], "FAIL")
        self.assertEqual(result["content_class"], "SPEECH_PROMISE")
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_concern_only_is_held(self):
        result = self.signals(
            "학생인권조례 폐지는 교육 격차와 갈등을 초래할 수 있어 우려됩니다"
        )
        self.assertEqual(result["precheck_status"], "HOLD")
        self.assertEqual(result["content_class"], "CONCERN_OR_ATTRIBUTED_CLAIM")

    def test_procedure_numbers_are_not_measurements(self):
        result = self.signals(
            "제4항과 제41조에 따라 11대 의회 상임위원을 선임하고 전자투표로 표결합니다"
        )
        self.assertEqual(result["precheck_status"], "FAIL")
        self.assertEqual(result["content_class"], "PARLIAMENTARY_PROCEDURE")
        self.assertEqual(result["substantive_values"], [])
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_navigation_is_rejected_for_verification(self):
        result = self.signals(
            "본문 바로가기 메뉴 로그인 회원가입 분야 선택 파일내려받기 전체 설명보기",
            self.open_data,
            "CONTEXT_WINDOW",
        )
        self.assertEqual(result["content_class"], "NAVIGATION")
        self.assertFalse(result["verification_usable"])

    def test_research_title_without_body_is_held(self):
        result = self.signals("집합건물 분쟁실태와 지원방안", self.research, "LINK_LABEL")
        self.assertEqual(result["content_class"], "DOCUMENT_TITLE_ONLY")
        self.assertEqual(result["precheck_status"], "HOLD")

    def test_table_heading_without_values_is_held(self):
        result = self.signals("2026.7월 지역별 체불 현황", self.labor, "PAGE_CHUNK")
        self.assertEqual(result["content_class"], "TABLE_SCHEMA_WITHOUT_VALUE")
        self.assertEqual(result["precheck_status"], "HOLD")

    def test_contact_footer_is_rejected(self):
        result = self.signals(
            "서울특별시청 (04524) 서울특별시 중구 세종대로 110 · 문의 및 전화민원 신청: 02)120",
            {
                "id": "eungdapso", "name": "응답소", "local": True,
                "voice": True, "role": "DISCOVERY",
            },
            "CONTEXT_WINDOW",
        )
        self.assertEqual(result["content_class"], "CONTACT_BOILERPLATE")
        self.assertEqual(result["precheck_status"], "FAIL")
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_budget_input_without_observed_outcome_is_held(self):
        result = self.signals(
            "서울시는 1조 4,570억 원 추경을 편성해 교통비 부담을 낮추고 피해지원 재원을 투입했습니다"
        )
        self.assertEqual(result["content_class"], "POLICY_ANNOUNCEMENT")
        self.assertEqual(result["precheck_status"], "HOLD")
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_data_portal_display_notice_is_rejected(self):
        result = self.signals(
            "※ 가장 최근에 개방된 100개 데이터만 표시됩니다.",
            self.open_data,
            "PAGE_CHUNK",
        )
        self.assertEqual(result["content_class"], "PLATFORM_NOTICE")
        self.assertFalse(result["verification_usable"])

    def test_foreign_card_total_is_decomposable(self):
        result = self.signals("서울 외국인 카드소비 총액 1조 원 자치구별·업종별 현황")
        self.assertEqual(result["precheck_status"], "PASS")
        self.assertEqual(result["evidence_anchor"], "DECOMPOSABLE_STRUCTURE")
        self.assertIn("1조 원", result["substantive_values"])

    def test_ud_taxi_question_does_not_invent_scene(self):
        text = (
            "서울 UD택시는 12대만 06~15시 운행해 요청과 매칭될 확률이 낮아 "
            "이용이 제한된다는 지적"
        )
        _, _, _, result = scout.score_text(text, self.council)
        self.assertNotEqual(result["evidence_anchor"], "NONE")
        payload = scout.build_question_payload(text, "council_minutes", result)
        self.assertEqual(payload["grounding_status"], "PASS")
        self.assertNotIn("병원", payload["question"])
        self.assertNotIn("미배차", payload["question"])

    def test_bus_claim_keeps_attribution_and_neutral_question(self):
        text = (
            "서울 시내버스 소송 부담을 협회는 5,266억 원에서 1조 216억 원으로 추산했고 "
            "연간 적자지원은 8,915억 원이다"
        )
        _, _, _, result = scout.score_text(text, self.council)
        self.assertEqual(result["evidence_anchor"], "MEASURED_PROBLEM_SIGNAL")
        self.assertEqual(result["claim_status"], "ATTRIBUTED_CLAIM")
        payload = scout.build_question_payload(text, "council_minutes", result)
        self.assertEqual(payload["grounding_status"], "PASS")
        self.assertNotIn("관리 공백", payload["question"])

    def test_high_score_navigation_cannot_reenter_verification_map(self):
        fake_record = {
            "source_id": "seoul_open_data",
            "source_name": "열린데이터",
            "score": 99,
            "qualified": True,
            "verification_usable": False,
            "grounding_status": "PASS",
            "text": "메뉴 문구",
            "url": "https://example.invalid",
            "question": "검증?",
        }

        class FakeModule:
            @staticmethod
            def run_source(source):
                metric = {
                    "id": source["id"], "name": source["name"], "role": source["role"],
                    "http_ok": True, "status": 200, "status_detail": "DEGRADED_NO_DATASET_TEXT",
                    "requests": 1, "failed_requests": 0, "extracted": 1,
                    "precheck_pass": 0, "grounded": 1, "qualified": 1,
                }
                return metric, [fake_record]

        FakeModule.SOURCES = [self.open_data]
        built = feed.build_feed(FakeModule)
        self.assertEqual(built["verification_map"], [])

    def test_question_numbers_are_subset_of_source_numbers(self):
        text = "서울 외국인 카드소비 총액 1조 원 자치구별 현황"
        result = self.signals(text)
        payload = scout.build_question_payload(text, "council_minutes", result)
        self.assertEqual(payload["grounding_status"], "PASS")


if __name__ == "__main__":
    unittest.main()
