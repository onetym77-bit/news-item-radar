import json
import tempfile
import unittest
from pathlib import Path

import review_youtube_context as module


def config():
    return json.loads(module.CONFIG.read_text(encoding="utf-8"))


def record(video_id, channel, archetype, *, seoul=False, signal=True,
           title="월세 부담 때문에 다른 동네로 이사했습니다", description=""):
    return {
        "id": video_id,
        "title": title,
        "channel": channel,
        "description": description,
        "published_at": "2026-09-27T00:00:00Z",
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "source_archetype": archetype,
        "seoul_place_terms": ["서울"] if seoul else [],
        "signal_markers": ["이사"] if signal else [],
        "first_person_markers": ["제가"],
        "verification_markers": ["만원"],
        "is_short": False,
        "views": 100,
        "query_labels": [{
            "agenda": "HOUSING",
            "cluster": "주거비 때문에 이동",
            "lane": "SCENE",
            "query": "월세 때문에 이사",
        }],
    }


def answer(cluster, quote=None):
    anchor = cluster["videos"][0]
    return {"assessments": [{
        "cluster_id": cluster["cluster_id"],
        "verdict": "REVIEW",
        "anchor_video_id": anchor["video_id"],
        "anchor_quote": quote or anchor["title"],
        "observed_pattern": "서로 다른 두 시민이 주거비 부담 뒤 실제 이사를 선택했다고 말한다.",
        "seoul_connection": "한 영상은 서울 거주와 이동 지역을 내용 안에서 직접 밝힌다.",
        "repetition_basis": "독립된 두 채널에서 같은 비용 부담과 이사 선택이 각각 나타난다.",
        "citizen_stake_to_check": "비슷한 조건의 세입자에게 이동이 선택인지 밀려남인지 확인해야 한다.",
        "test_question": "서울 세입자의 이사가 주거비 상승 때문에 강제된 선택이었는가?",
        "alternative_explanation": "직장 이동이나 가족 변화가 이사의 주된 이유였을 수 있다.",
        "first_check": "두 영상 당사자에게 이사 전후 비용과 다른 이사 이유를 먼저 확인한다.",
        "scene_path": "이사 전후 집과 생활권, 비용 문서, 당사자 인터뷰를 비교할 수 있다.",
        "reason": "검색어가 아니라 실제 행동 변화가 두 독립 영상에서 반복된다.",
    }]}


class YoutubeSemanticShadowTests(unittest.TestCase):
    def test_selects_repeated_direct_signal_with_seoul_in_supporting_video(self):
        rows = [
            record("a", "시민A", "당사자 가능성", seoul=True),
            record("b", "현장B", "현장·운영자"),
        ]
        selected, excluded = module.select_clusters(rows, {}, 3)
        self.assertEqual(len(selected), 1)
        self.assertEqual(excluded, [])
        self.assertEqual(selected[0]["independent_qualified_channels"], 2)
        self.assertEqual(selected[0]["seoul_supporting_records"], 1)

    def test_legal_advice_channels_are_not_direct_citizen_signal(self):
        rows = [
            record("a", "법률A", "상담·지원", seoul=True),
            record("b", "법률B", "상담·지원"),
        ]
        selected, _ = module.select_clusters(rows, {}, 3)
        self.assertEqual(selected, [])

    def test_incidental_seoul_in_disallowed_video_does_not_localize_cluster(self):
        rows = [
            record("a", "시민A", "당사자 가능성"),
            record("b", "현장B", "현장·운영자"),
            record("c", "뉴스C", "언론·방송", seoul=True),
        ]
        selected, excluded = module.select_clusters(rows, {}, 3)
        self.assertEqual(selected, [])
        self.assertIn("서울 사건 지역 단서 없음", excluded[0]["reason"])

    def test_ai_fiction_or_pending_rows_cannot_supply_repetition(self):
        rows = [
            record("a", "시민A", "당사자 가능성", seoul=True),
            record("b", "창작B", "사연·재연"),
            record("c", "대기C", "분류 대기"),
        ]
        selected, _ = module.select_clusters(rows, {}, 3)
        self.assertEqual(selected, [])

    def test_cluster_specific_outcome_rejects_generic_rent_vlogs(self):
        rows = [
            record(
                "a", "시민A", "당사자 가능성", seoul=True,
                title="서울에서 월세 120만원 자취 브이로그", signal=False),
            record(
                "b", "시민B", "당사자 가능성",
                title="월세 65만원 원룸 생활 브이로그", signal=False),
            record(
                "c", "설명C", "현장·운영자",
                title="관리비가 올랐습니다", signal=True),
            record(
                "d", "설명D", "현장·운영자",
                title="관리비를 못 받았습니다", signal=True),
        ]
        selected, excluded = module.select_clusters(rows, config(), 3)
        self.assertEqual(selected, [])
        self.assertIn("결과 행동 영상 2개 미만", excluded[0]["reason"])

    def test_validates_contiguous_anchor_and_keeps_shadow_boundary(self):
        selected, _ = module.select_clusters([
            record("a", "시민A", "당사자 가능성", seoul=True),
            record("b", "현장B", "현장·운영자"),
        ], {}, 3)
        result = module.validate_assessments(selected, answer(selected[0]))
        self.assertEqual(result[0]["verdict"], "REVIEW")
        self.assertFalse(result[0]["production_eligible"])
        self.assertEqual(result[0]["briefing_output"], "NONE")

    def test_nonexistent_quote_is_downgraded_to_hold(self):
        selected, _ = module.select_clusters([
            record("a", "시민A", "당사자 가능성", seoul=True),
            record("b", "현장B", "현장·운영자"),
        ], {}, 3)
        result = module.validate_assessments(
            selected, answer(selected[0], "원문에는 전혀 없는 문장입니다"))
        self.assertEqual(result[0]["verdict"], "HOLD")
        self.assertNotIn("production_eligible", result[0])

    def test_dry_run_writes_prefilter_only_without_model_call(self):
        rows = [
            record("a", "시민A", "당사자 가능성", seoul=True),
            record("b", "현장B", "현장·운영자"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger, config, output = root / "ledger.json", root / "config.json", root / "out.json"
            ledger.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            config.write_text(module.CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
            payload = module.run(ledger, config, output, "test", dry_run=True)
            self.assertEqual(payload["status"], "PREFILTER_ONLY")
            self.assertEqual(payload["model_calls"], 0)
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()

