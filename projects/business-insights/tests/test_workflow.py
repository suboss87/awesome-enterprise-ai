import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
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
        out=self.run_case();self.assertEqual(out['answer_status'],'calculated')
        self.assertEqual(out['metrics']['total'],'1900.00')
        self.assertEqual(out['table'][0]['record_ids'],['S1'])
    def test_refund_and_cost_not_gross_revenue(self):
        self.plan['measure']='gross_profit';self.assertEqual(self.run_case()['metrics']['total'],'750.00')
    def test_date_filter_inclusive(self):
        self.plan['end_date']='2026-09-05';self.assertEqual(self.run_case()['metrics']['matched_records'],1)
    def test_regions_filter(self):
        self.plan['regions']=['South'];self.assertEqual(self.run_case()['metrics']['total'],'800.00')
    def test_no_cross_currency_addition(self):
        self.data['records'][1]['currency']='EUR';self.plan['currency']=''
        out=self.run_case()
        self.assertEqual(out['answer_status'],'withheld')
        self.assertEqual([f['code'] for f in out['findings']],['mixed_currency'])
        self.assertNotIn('total',out['metrics']);self.assertEqual(out['table'],[])
    def test_explicit_currency_filters(self):
        self.data['records'][1]['currency']='EUR';self.assertEqual(self.run_case()['metrics']['total'],'1100.00')
    def test_unsupported_request_needs_clarification(self):
        self.plan.update(status='clarify',clarification='Which profit definition?')
        out=self.run_case();self.assertEqual(out['answer_status'],'withheld')
        self.assertEqual(out['plan']['status'],'clarify')
        self.assertEqual(out['findings'][0]['code'],'clarification')

    def test_ambiguous_profit_cannot_become_a_model_selected_metric(self):
        for question in ('How profitable were we in September 2026?',
                         'Show our profit for September 2026.',
                         'What was profitability last month?',
                         'What were our profits in USD?',
                         'I do not mean gross profit. How profitable were we in September 2026?',
                         'Do not calculate gross profit. Show profit in September 2026.'):
            with self.subTest(question=question):
                self.data['question']=question
                ai=ReplayAI([]);out=load('business-insights').run(self.data,ai)
                self.assertEqual(out['answer_status'],'withheld')
                self.assertEqual(out['plan']['status'],'clarify')
                self.assertNotIn('total',out['metrics'])
                self.assertEqual(ai.calls,[])

    def test_explicit_gross_profit_is_still_supported(self):
        self.data['question']='How much gross profit did we have in September 2026 in USD?'
        self.plan.update(measure='gross_profit',question_quote=self.data['question'])
        self.assertEqual(self.run_case()['metrics']['total'],'750.00')
    def test_unknown_region_is_not_zero_answer(self):
        self.plan['regions']=['West'];out=self.run_case()
        self.assertEqual(out['answer_status'],'withheld')
        self.assertEqual(out['findings'][0]['code'],'unknown_filter')
        self.assertNotIn('total',out['metrics']);self.assertEqual(out['table'],[])
    def test_empty_period_is_not_zero_business(self):
        self.plan.update(start_date='2026-09-01',end_date='2026-09-01')
        out=self.run_case();self.assertEqual(out['answer_status'],'withheld')
        self.assertEqual(out['findings'][0]['code'],'no_data')
        self.assertEqual(out['metrics']['matched_records'],0)
        self.assertIsNone(out['metrics']['total']);self.assertEqual(out['table'],[])

    def test_incomplete_snapshot_is_withheld_before_model_call(self):
        self.data['source_snapshot']['completeness']='partial'
        ai=ReplayAI([]);out=load('business-insights').run(self.data,ai)
        self.assertEqual(out['answer_status'],'withheld')
        self.assertEqual(out['findings'][0]['code'],'snapshot_incomplete')
        self.assertEqual(ai.calls,[])
        self.assertNotIn('total',out['metrics'])

    def test_untrusted_freshness_and_definition_states_are_withheld_before_model(self):
        for field,value,code in [('freshness','stale','snapshot_freshness'),
                                 ('freshness','unknown','snapshot_freshness'),
                                 ('metric_definition_status','unapproved','metric_definition_unapproved'),
                                 ('metric_definition_status','unknown','metric_definition_unapproved')]:
            with self.subTest(field=field,value=value):
                self.data['source_snapshot'][field]=value
                ai=ReplayAI([]);out=load('business-insights').run(self.data,ai)
                self.assertEqual(out['answer_status'],'withheld')
                self.assertEqual(out['findings'][0]['code'],code)
                self.assertEqual(ai.calls,[])
                self.assertNotIn('total',out['metrics'])
                self.data['source_snapshot'][field]='current' if field=='freshness' else 'approved'

    def test_period_outside_complete_snapshot_is_withheld(self):
        self.plan['start_date']='2026-08-01'
        out=self.run_case()
        self.assertEqual(out['answer_status'],'withheld')
        self.assertEqual(out['findings'][0]['code'],'snapshot_coverage')
        self.assertNotIn('total',out['metrics']);self.assertEqual(out['table'],[])

    def test_entirely_later_or_earlier_period_is_withheld(self):
        for start,end in [('2026-10-01',''),('','2026-08-30')]:
            with self.subTest(start=start,end=end):
                self.plan['start_date']=start;self.plan['end_date']=end
                out=self.run_case()
                self.assertEqual(out['answer_status'],'withheld')
                self.assertEqual(out['findings'][0]['code'],'snapshot_coverage')
                self.assertNotIn('total',out['metrics'])
        self.plan['start_date']='';self.plan['end_date']=''

    def test_record_outside_declared_coverage_is_rejected(self):
        self.data['source_snapshot']['coverage_start']='2026-09-01'
        with self.assertRaises(InputError):self.run_case()

    def test_snapshot_identity_and_coverage_are_returned_for_review(self):
        out=self.run_case()
        self.assertEqual(out['source_snapshot']['snapshot_id'],'sample-sales-close-2026-09')
        self.assertEqual(out['coverage'],{'start':'2026-08-31','end':'2026-09-30'})

    def test_later_question_as_of_can_use_an_older_complete_snapshot(self):
        self.data['as_of']='2026-10-02'
        self.assertEqual(self.run_case()['answer_status'],'calculated')

    def test_snapshot_export_time_requires_timezone(self):
        self.data['source_snapshot']['exported_at']='2026-10-09T08:00:00'
        with self.assertRaises(InputError):self.run_case()

    def test_export_cannot_precede_its_declared_business_data(self):
        self.data['source_snapshot']['exported_at']='2020-01-01T00:00:00+00:00'
        ai=ReplayAI([])
        with self.assertRaises(InputError):load('business-insights').run(self.data,ai)
        self.assertEqual(ai.calls,[])

    def test_export_uses_declared_source_timezone_calendar_day(self):
        self.data['source_snapshot']['exported_at']='2026-09-30T00:15:00+14:00'
        self.assertEqual(self.run_case()['answer_status'],'calculated')

    def test_snapshot_export_time_accepts_both_offset_signs(self):
        for stamp in ('2026-10-09T08:00:00Z','2026-10-09T08:00:00+05:30','2026-10-09T08:00:00-05:00'):
            with self.subTest(stamp=stamp):
                self.data['source_snapshot']['exported_at']=stamp
                self.assertEqual(self.run_case()['answer_status'],'calculated')

    def test_cli_keeps_ready_plan_distinct_from_withheld_answer(self):
        self.data['records'][1]['currency']='EUR';self.plan['currency']=''
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);input_path=root/'input.json';responses_path=root/'responses.json'
            input_path.write_text(json.dumps(self.data));responses_path.write_text(json.dumps([self.plan]))
            completed=subprocess.run([sys.executable,'-m','enterprise_ai','run','business-insights',
                '--input',str(input_path),'--mode','replay','--responses',str(responses_path)],
                cwd=ROOT.parents[1],capture_output=True,text=True,timeout=10)
        self.assertEqual(completed.returncode,0,completed.stderr)
        result=json.loads(completed.stdout)
        self.assertEqual(result['plan']['status'],'ready')
        self.assertEqual(result['answer_status'],'withheld')
        self.assertEqual([f['code'] for f in result['findings']],['mixed_currency'])
        self.assertNotIn('total',result['metrics']);self.assertEqual(result['table'],[])
    def test_duplicate_source_rejected(self):
        self.data['records'].append(copy.deepcopy(self.data['records'][0]))
        with self.assertRaises(InputError):self.run_case()
    def test_currency_must_use_ascii_letters(self):
        self.data['records'][0]['currency']='ÜSD'
        ai=ReplayAI([])
        with self.assertRaises(InputError):load('business-insights').run(self.data,ai)
        self.assertEqual(ai.calls,[])

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
