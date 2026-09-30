import copy
import json
from pathlib import Path
import unittest
from enterprise_ai.catalog import load
from enterprise_ai.common import ReplayAI, InputError

ROOT=Path(__file__).resolve().parents[1]


class BusinessInsightsTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((ROOT/'examples/input.json').read_text())
        self.plan=json.loads((ROOT/'examples/responses.json').read_text())[0]
    def run_case(self):
        return load('business-insights').run(self.data,ReplayAI([self.plan]))
    def test_exact_net_revenue(self):
        out=self.run_case();self.assertEqual(out['metrics']['total'],'1900.00')
        self.assertEqual(out['table'][0]['record_ids'],['S1'])
    def test_refund_and_cost_not_gross_revenue(self):
        self.plan['measure']='gross_profit';self.assertEqual(self.run_case()['metrics']['total'],'750.00')
    def test_date_filter_inclusive(self):
        self.plan['end_date']='2026-09-05';self.assertEqual(self.run_case()['metrics']['matched_records'],1)
    def test_regions_filter(self):
        self.plan['regions']=['South'];self.assertEqual(self.run_case()['metrics']['total'],'800.00')
    def test_no_cross_currency_addition(self):
        self.data['records'][1]['currency']='EUR';self.plan['currency']=''
        self.assertEqual(self.run_case()['findings'][0]['code'],'mixed_currency')
    def test_explicit_currency_filters(self):
        self.data['records'][1]['currency']='EUR';self.assertEqual(self.run_case()['metrics']['total'],'1100.00')
    def test_unsupported_request_needs_clarification(self):
        self.plan.update(status='clarify',clarification='Which profit definition?')
        self.assertEqual(self.run_case()['findings'][0]['code'],'clarification')
    def test_unknown_region_is_not_zero_answer(self):
        self.plan['regions']=['West'];self.assertEqual(self.run_case()['findings'][0]['code'],'unknown_filter')
    def test_empty_period_is_not_zero_business(self):
        self.plan.update(start_date='2025-01-01',end_date='2025-01-31')
        self.assertEqual(self.run_case()['findings'][0]['code'],'no_data')
    def test_duplicate_source_rejected(self):
        self.data['records'].append(copy.deepcopy(self.data['records'][0]))
        with self.assertRaises(InputError):self.run_case()
    def test_float_money_rejected(self):
        self.data['records'][0]['revenue']=1200.0
        with self.assertRaises(InputError):self.run_case()
    def test_inverted_dates_rejected(self):
        self.plan['start_date']='2027-01-01'
        with self.assertRaises(InputError):self.run_case()
    def test_hallucinated_question_quote_rejected(self):
        self.plan['question_quote']='DROP TABLE orders'
        with self.assertRaises(InputError):self.run_case()
    def test_no_arbitrary_query_field(self):
        self.plan['sql']='DELETE FROM orders'
        with self.assertRaises(InputError):self.run_case()


if __name__=='__main__':unittest.main()
