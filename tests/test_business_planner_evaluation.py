"""Check independent labeled arithmetic and evaluation accounting, without API calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from enterprise_ai.catalog import load
from enterprise_ai.common import ReplayAI
from scripts.evaluate_business_planner import compare,normalize,oracle,narrow_rules,save

ROOT=Path(__file__).resolve().parents[1]
CASES=json.loads((ROOT/'projects/business-insights/evaluation/planner-2026-10-09/cases.json').read_text())['cases']


class PlannerEvaluationTests(unittest.TestCase):
    def test_independently_labeled_arithmetic_and_withholding(self):
        for case in CASES:
            with self.subTest(case=case['id']):
                output=load('business-insights').run(copy.deepcopy(case['input']),ReplayAI([oracle(case)]))
                comparison=compare(output,case['expected'],case['input'])
                for key in ('strict_plan_agreement','answer_status_agreement','metrics_agreement','table_agreement'):
                    self.assertTrue(comparison[key],key)
                self.assertFalse(comparison['false_ready'])

    def test_safe_clarification_is_not_strict_plan_agreement(self):
        case=next(c for c in CASES if c['id']=='money-currency-unspecified')
        plan=oracle(case);plan.update(status='clarify',clarification='Choose a currency.')
        output=load('business-insights').run(case['input'],ReplayAI([plan]))
        comparison=compare(output,case['expected'],case['input'],allow_safe_clarification=True)
        self.assertTrue(comparison['safe_clarification_equivalent'])
        self.assertTrue(comparison['answer_status_agreement'])
        self.assertFalse(comparison['strict_plan_agreement'])

    def test_empty_day_clarification_has_no_equivalence_credit(self):
        case=next(c for c in CASES if c['id']=='covered-empty-day-not-zero')
        plan=oracle(case);plan.update(status='clarify',clarification='No rows.')
        output=load('business-insights').run(case['input'],ReplayAI([plan]))
        self.assertFalse(compare(output,case['expected'],case['input'])['safe_clarification_equivalent'])

    def test_missing_null_metric_is_not_a_match(self):
        case=next(c for c in CASES if c['id']=='covered-empty-day-not-zero')
        output=load('business-insights').run(case['input'],ReplayAI([oracle(case)]))
        del output['metrics']['total']
        self.assertFalse(compare(output,case['expected'],case['input'])['metrics_agreement'])

    def test_false_calculation_is_counted_separately(self):
        case=next(c for c in CASES if c['id']=='ambiguous-profit-meaning')
        output=json.loads((ROOT/'projects/business-insights/evaluation/planner-2026-10-09/trial/09-live/output.json').read_text())
        self.assertTrue(compare(output,case['expected'],case['input'])['false_ready'])

    def test_rules_do_not_invent_a_filter_from_grouping(self):
        case=next(c for c in CASES if c['id']=='net-after-refunds-by-product')
        self.assertEqual(narrow_rules(case['input'])['products'],[])

    def test_manifest_and_results_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'result.json';save(path,{'original':True})
            with self.assertRaises(FileExistsError):save(path,{'replacement':True})
            self.assertEqual(json.loads(path.read_text()),{'original':True})

    def test_unspecified_money_currency_normalizes_only_when_unambiguous(self):
        case=CASES[0];plan=oracle(case);plan['currency']=''
        self.assertEqual(normalize(plan,case['input'])['currency'],'USD')
        mixed=next(c for c in CASES if c['id']=='money-currency-unspecified')
        self.assertEqual(normalize(plan,mixed['input'])['currency'],'')


if __name__=='__main__':unittest.main()
