import unittest

from contract_route_probe import (
    Scripts, first_entries, function_body, inspect_route, official_script_urls,
    parse_call, route_evidence,
)

class ContractRouteTests(unittest.TestCase):
    def test_call_args_and_installment_are_distinct(self):
        contract = parse_call("cmdPopInfo('6172026091099','R26TA02223024','1차','R26TA02223024|1차');")
        payment = parse_call("cmdPopInfo('6222025052698','R25TA00570579','R25TA00570579');")
        self.assertEqual(contract["contract_id"], "R26TA02223024")
        self.assertEqual(contract["installment"], "1차")
        self.assertEqual(payment["contract_id"], "R25TA00570579")
        self.assertIsNone(payment["installment"])

    def test_executable_or_malformed_call_is_rejected(self):
        self.assertIsNone(parse_call("cmdPopInfo('1',alert(1),'x');"))
        self.assertIsNone(parse_call("cmdPopInfo('6172026091099','R26TA02223024');"))
        self.assertIsNone(parse_call("cmdPopInfo('6172026091099','R26TA02223024','1차');evil()"))

    def test_same_contract_payments_are_not_new_projects(self):
        html = "".join(
            f'<a onclick="cmdPopInfo(\'6222025052698\',\'R25TA00570579\',\'R25TA00570579\');">기성 {n}</a>'
            for n in range(3)
        )
        result = inspect_route("C_PAYMENTS", html)
        self.assertTrue(result["same_contract_in_first_five"])
        self.assertEqual(result["entry_count_checked"], 3)
        self.assertEqual(result["detail_fetch"], "NOT_ATTEMPTED")

    def test_inline_function_yields_route_not_detail_success(self):
        html = ('<script>function cmdPopInfo(a,b,c){'
                'window.open("/TotalAlimi_new/CnrtPop.action?key="+a);'
                '}</script>'
                '<a onclick="cmdPopInfo(\'6172026091099\',\'R26TA02223024\',\'1차\');">공사</a>')
        result = inspect_route("C_LIST", html)
        self.assertEqual(result["inline_route"]["function_status"], "FOUND")
        self.assertIn("window.open", result["inline_route"]["transport_hints"])
        self.assertEqual(result["detail_fetch"], "NOT_ATTEMPTED")
        self.assertEqual(result["article_gate"], "NOT_EVALUATED")

    def test_scripts_and_external_urls_stay_bounded_and_same_host(self):
        scripts = Scripts('<script src="/a.js"></script>'
                          '<script src="https://evil.example/b.js"></script>'
                          '<script src="/x.css"></script>')
        self.assertEqual(official_script_urls(scripts.sources,
                         "https://cis.seoul.go.kr/TotalAlimi_new/CnrtList.action"),
                         ["https://cis.seoul.go.kr/a.js"])

    def test_route_absence_is_explicit(self):
        result = route_evidence(["function unrelated(){return 1;}"])
        self.assertEqual(result["function_status"], "NOT_FOUND")
        self.assertEqual(result["action_paths"], [])

if __name__ == "__main__":
    unittest.main()
