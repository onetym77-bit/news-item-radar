import json
import unittest

import collect_source_material_v2_1 as module


def config():
    return json.loads(module.CONFIG.read_text(encoding="utf-8"))


class YoutubeClassificationTests(unittest.TestCase):
    def test_office_address_after_promotion_footer_is_not_event_location(self):
        cfg = config()
        terms = module.seoul_event_matches(
            "보증금 1억 6천 안 주던 집주인의 최후",
            "새 세입자 올 때까지 돈을 못 준 실제 사건입니다. "
            "무료법률상담 02-000-0000 주소 : 서울특별시 서초구 법원로",
            cfg,
        )
        self.assertEqual(terms, [])

    def test_seoul_in_title_remains_event_location(self):
        cfg = config()
        terms = module.seoul_event_matches(
            "서울에서 월세 때문에 이사했습니다",
            "이사 전후 생활을 기록했습니다.",
            cfg,
        )
        self.assertIn("서울", terms)

    def test_explainer_with_source_markers_is_not_direct_experience(self):
        cfg = config()
        settings = cfg["youtube_discovery"]
        title = '"제가 낸 관리비는 올랐습니다" 경비비의 구조'
        description = (
            "이 영상은 공개 자료를 근거로 관리비 구조를 정리해 설명합니다. "
            "출처는 고정 댓글에 있습니다."
        )
        archetype = module.classify_source("노후가계부", title, description, settings)
        self.assertEqual(archetype, "생활정보·설명")
        promoted = module.promote_direct_experience(
            archetype, "노후가계부", title, description, settings,
            [{"lane": "EVIDENCE"}],
        )
        self.assertEqual(promoted, "생활정보·설명")

    def test_generic_first_person_quote_does_not_make_direct_experience(self):
        cfg = config()
        settings = cfg["youtube_discovery"]
        result = module.promote_direct_experience(
            "분류 대기", "일반채널", '"제가 낸 관리비는 올랐습니다"',
            "관리비 구조를 살펴봅니다.", settings, [{"lane": "EVIDENCE"}],
        )
        self.assertEqual(result, "분류 대기")

    def test_source_lane_vlog_can_remain_possible_direct_experience(self):
        cfg = config()
        settings = cfg["youtube_discovery"]
        result = module.promote_direct_experience(
            "분류 대기", "서울자취", "월세 자취 브이로그",
            "직접 살며 기록한 일상입니다.", settings, [{"lane": "SOURCE"}],
        )
        self.assertEqual(result, "당사자 가능성")

    def test_normalization_keeps_raw_place_but_separates_event_place(self):
        cfg = config()
        row = {
            "id": "law",
            "title": "보증금을 못 받은 실제 사건",
            "channel": "부동산 전문변호사",
            "description": (
                "의뢰인의 보증금 반환 사건입니다. "
                "무료법률상담 02-000-0000 주소 : 서울특별시 서초구 법원로"
            ),
            "query_labels": [{
                "agenda": "HOUSING", "cluster": "보증금 반환 지연",
                "lane": "BEHAVIOR", "query": "보증금 못 받아 이사 못 가",
            }],
        }
        normalized = module.normalize_record(row, cfg)
        self.assertIn("서울", normalized["seoul_place_terms"])
        self.assertEqual(normalized["seoul_event_terms"], [])
        self.assertEqual(normalized["source_archetype"], "상담·지원")


if __name__ == "__main__":
    unittest.main()
