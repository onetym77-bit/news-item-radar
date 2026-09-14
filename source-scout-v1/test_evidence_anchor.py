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


scout = load_module("source_scout_anchor_test", "scout_sources.py")
feed = load_module("source_feed_anchor_test", "collect_daily_feed.py")


class EvidenceAnchorTests(unittest.TestCase):
    def setUp(self):
        self.council = {
            "id": "council_minutes",
            "name": "서울시의회 회의록",
            "local": True,
            "voice": False,
            "role": "BOTH",
        }
        self.voice = {
            "id": "eungdapso",
            "name": "서울시 응답소 공개민원",
            "local": True,
            "voice": True,
            "role": "DISCOVERY",
        }

    def test_routine_accessibility_project_is_not_a_problem_anchor(self):
        text = "천왕산 책쉼터 장애물 없는 생활환경 조성공사 49백만원 2026년"
        _, reasons, _, signals = scout.score_text(text, self.council)
        self.assertEqual(signals["evidence_anchor"], "NONE")
        self.assertIn("사업·공사명 단독", reasons)
        self.assertEqual(
            scout.question_for(text, self.council),
            "근거 앵커 없음 — 질문 점수 평가 제외",
        )

    def test_routine_project_is_not_qualified_from_keywords_and_year(self):
        text = "천왕산 책쉼터 장애물 없는 생활환경 조성공사 49백만원 2026년"
        parser = scout.parse_html(f"<p>{text}</p>")
        rows = scout.extract_records(
            parser,
            "https://ms.smc.seoul.kr/kr/assembly/main.do",
            self.council,
            include_windows=False,
        )
        self.assertTrue(rows)
        self.assertFalse(rows[0]["qualified"])

    def test_direct_experience_can_enter_as_claim_not_verified_harm(self):
        text = "서울 시민이 버스를 2시간 대기해 불편을 겪었다는 민원"
        _, _, _, signals = scout.score_text(text, self.voice)
        self.assertEqual(signals["evidence_anchor"], "DIRECT_PROBLEM_SIGNAL")

    def test_measured_deviation_is_a_problem_signal(self):
        text = "서울 임금체불 건수가 지난해보다 20% 증가"
        _, _, _, signals = scout.score_text(text, self.council)
        self.assertEqual(signals["evidence_anchor"], "MEASURED_PROBLEM_SIGNAL")

    def test_decomposable_total_can_enter_without_a_victim_case(self):
        text = "서울 외국인 카드소비 총액 1조 원 자치구별 현황"
        _, _, _, signals = scout.score_text(text, self.council)
        self.assertEqual(signals["evidence_anchor"], "DECOMPOSABLE_STRUCTURE")
        self.assertIn("지역·대상·시간", scout.question_for(text, self.council))

    def test_change_in_routine_project_can_be_an_anchor(self):
        text = "서울 노후시설 개선공사 비용이 5억원 증가"
        _, _, _, signals = scout.score_text(text, self.council)
        self.assertEqual(signals["evidence_anchor"], "MEASURED_PROBLEM_SIGNAL")

    def test_daily_feed_defense_does_not_invent_a_victim(self):
        question = feed.discovery_question(
            {"text": "서울 시설 정비사업", "evidence_anchor": "NONE"}
        )
        self.assertEqual(question, "근거 앵커 없음 — 질문 점수 평가 제외")


if __name__ == "__main__":
    unittest.main()
