import unittest

from construction_change_probe import (
    describe_link, exact_contract_join, inspect_list, inspect_progress,
    registration_date, row_context,
)

class ChangeLinkTests(unittest.TestCase):
    def test_registration_date_is_row_level_only(self):
        self.assertEqual(registration_date("공사 등록일 : 2026-09-15"),
                         "2026-09-15")
        self.assertIsNone(registration_date("공사기간 2026-09-15"))

    def test_popup_args_are_diagnostics_not_join_proof(self):
        link = describe_link({
            "onclick": "cmdPopInfo('123456789','R26TA02228982');",
            "href": "#none",
        })
        self.assertEqual(link["function"], "cmdPopInfo")
        self.assertEqual(link["quoted_args"], ["123456789", "R26TA02228982"])
        self.assertEqual(link["project_ids_named"], [])
        self.assertEqual(link["first_arg_project_candidate"], "123456789")

    def test_explicit_project_id_can_join_exactly(self):
        items = [{
            "title": "사업 A",
            "link": {"project_ids_named": ["6112026091499"]},
        }]
        contracts = [{"record_key": "6112026091499", "title": "사업 A"}]
        result = exact_contract_join(items, contracts, {"function_status": "NOT_FOUND"})
        self.assertEqual(len(result["exact_project_id_matches"]), 1)
        self.assertEqual(result["title_only_join"], "NOT_ACCEPTED")

    def test_first_argument_requires_official_pjt_cd_route(self):
        items = [{
            "title": "사업 A",
            "link": {
                "project_ids_named": [],
                "first_arg_project_candidate": "6112026091499",
            },
        }]
        contracts = [{"record_key": "6112026091499", "title": "사업 A"}]
        route = {
            "function_status": "FOUND",
            "popup_expression": 'window.open("/PopInfo.action?pjt_cd="+pjt_cd);',
        }
        result = exact_contract_join(items, contracts, route)
        self.assertEqual(result["first_argument_semantics"],
                         "ROUTE_CONFIRMED_AS_PJT_CD")
        self.assertEqual(len(result["first_argument_overlaps"]), 1)
        self.assertEqual(result["exact_project_id_matches"], [])

    def test_same_title_without_id_cannot_join(self):
        items = [{
            "title": "사업 A",
            "link": {"project_ids_named": []},
        }]
        contracts = [{"record_key": "6112026091499", "title": "사업 A"}]
        self.assertEqual(exact_contract_join(items, contracts, {"function_status": "NOT_FOUND"})
                         ["exact_project_id_matches"], [])

    def test_first_five_rows_have_own_dates(self):
        html = (
            "<a onclick=\"cmdPopInfo('111111','R26TA02228982');\">첫 공사</a>"
            "<p>담당 강동구 등록일 : 2026-09-15</p>"
            "<a onclick=\"cmdPopInfo('222222','R26TA02228982');\">둘째 공사</a>"
            "<p>담당 양천구 등록일 : 2026-09-14</p>"
        )
        result = inspect_list(html, "DESIGN")
        self.assertEqual([x["registration_date"] for x in result["items"]],
                         ["2026-09-15", "2026-09-14"])
        self.assertEqual(result["snapshot_cadence"], "NOT_ESTABLISHED")
        self.assertEqual(result["article_gate"], "NOT_EVALUATED")

    def test_table_date_can_be_read_without_label(self):
        html = ('<a onclick="cmdPopInfo(\'6112026091499\',\'공사명\');">공사명</a>'
                '<td>강동구</td><td>0</td><td>2026-09-15</td>')
        result = inspect_list(html, "DESIGN")
        self.assertEqual(result["items"][0]["registration_date"], "2026-09-15")

    def test_duplicate_popup_anchor_not_counted_twice(self):
        html = ('<a onclick="cmdPopInfo(\'1112021020598\',\'1221\');">영동대로 공사</a>' * 2
                + '<a onclick="cmdPopInfo(\'1112021020598\',\'1222\');">영동대로 공사</a>')
        result = inspect_list(html, "PENALTY")
        self.assertEqual(len(result["items"]), 2)

    def test_progress_snippets_do_not_infer_registration(self):
        result = inspect_progress(
            "<h1>주요사업진행현황</h1><p>사업기간 : 2024-01-01 ~ "
            "2030-01-01 계획 : 10 % 실적 : 8 %</p>"
        )
        self.assertEqual(result["registration_date_status"], "NOT_OBSERVED")
        self.assertEqual(result["snapshot_cadence"], "NOT_ESTABLISHED")

if __name__ == "__main__":
    unittest.main()
