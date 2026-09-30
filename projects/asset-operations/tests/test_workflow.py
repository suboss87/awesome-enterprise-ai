"""Contract failures and frozen synthetic business scenarios; no model claims."""
import copy
import json
from pathlib import Path
import unittest
from enterprise_ai.catalog import load
from enterprise_ai.common import InputError, ReplayAI

ROOT=Path(__file__).resolve().parents[1]
SLUG=ROOT.name

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((ROOT/'examples/input.json').read_text())
        self.responses=json.loads((ROOT/'examples/responses.json').read_text())
        self.module=load(SLUG)
    def run_workflow(self):
        return self.module.run(self.data,ReplayAI(self.responses))
    def test_frozen_business_cases(self):
        cases=json.loads((ROOT/'evaluation/cases.json').read_text())['cases']
        self.assertGreaterEqual(len(cases),8)
        for case in cases:
            with self.subTest(case=case['id']):
                result=self.module.run(case['input'],ReplayAI(case['replay_responses']))
                for key,value in case['expected_metrics'].items():self.assertEqual(result['metrics'][key],value)
                self.assertEqual([f['code'] for f in result['findings']],case['expected_finding_codes'])
                self.assertTrue(result['human_review_required'])
    def test_unknown_input_field(self):
        self.data['auto_execute']=True
        with self.assertRaises(InputError):self.run_workflow()
    def test_duplicate_input_ids(self):
        field={'incident-operations':'events','exposure-review':'findings','inventory-decisions':'notes','asset-operations':'readings'}[SLUG]
        self.data[field].append(copy.deepcopy(self.data[field][0]))
        with self.assertRaises(InputError):self.run_workflow()
    def test_fabricated_quote(self):
        if SLUG=='incident-operations':entry=self.responses[0]['hypotheses'][0]['support'][0]
        elif SLUG=='exposure-review':entry=self.responses[0]['advisories'][0]['evidence'][0]
        elif SLUG=='inventory-decisions':entry=self.responses[0]['note_reviews'][0]['evidence'][0]
        else:entry=self.responses[0]['asset_reviews'][0]['evidence'][0]
        entry['quote']='This statement was never in the source.'
        with self.assertRaises(InputError):self.run_workflow()
    def test_foreign_source(self):
        if SLUG=='incident-operations':entry=self.responses[0]['hypotheses'][0]['support'][0]
        elif SLUG=='exposure-review':entry=self.responses[0]['advisories'][0]['evidence'][0]
        elif SLUG=='inventory-decisions':entry=self.responses[0]['note_reviews'][0]['evidence'][0]
        else:entry=self.responses[0]['asset_reviews'][0]['evidence'][0]
        entry['source_id']='some-other-customer'
        with self.assertRaises(InputError):self.run_workflow()
    def test_missing_model_result_fails(self):
        self.responses=[]
        with self.assertRaises(InputError):self.run_workflow()
    def test_required_evidence(self):
        if SLUG=='incident-operations':self.responses[0]['hypotheses'][0]['support']=[]
        elif SLUG=='exposure-review':self.responses[0]['advisories'][0]['evidence']=[]
        elif SLUG=='inventory-decisions':self.responses[0]['note_reviews'][0]['evidence']=[]
        else:self.responses[0]['asset_reviews'][0]['evidence']=[]
        with self.assertRaises(InputError):self.run_workflow()
    def test_invalid_domain_boundary(self):
        if SLUG=='incident-operations':self.data['events'][0]['at']='2026-09-01T12:00:00Z'
        elif SLUG=='exposure-review':self.data['advisories'][0]['fixed_versions']=['1.0']
        elif SLUG=='inventory-decisions':self.data['items'][0]['reserved']=6
        else:self.data['readings'][0]['at']='2026-09-02T10:00:00Z'
        with self.assertRaises(InputError):self.run_workflow()
    def test_second_domain_boundary(self):
        if SLUG=='incident-operations':self.data['events'][0]['at']='2026-09-01T10:00:00'
        elif SLUG=='exposure-review':self.data['findings'][0]['advisory_id']='not-provided'
        elif SLUG=='inventory-decisions':self.data['items'][0]['history'][0]['date']='2026-08-30'
        else:self.data['assets'][0]['persistence']=True
        with self.assertRaises(InputError):self.run_workflow()
    def test_deterministic_measurement(self):
        result=self.run_workflow()
        if SLUG=='incident-operations':self.assertEqual([e['id'] for e in result['timeline']],['log','deploy','alert'])
        elif SLUG=='exposure-review':self.assertEqual(result['matches'][0]['status'],'affected_version_match')
        elif SLUG=='inventory-decisions':self.assertEqual(result['plan'][0]['target_units'],22)
        else:self.assertEqual(result['statuses'][0]['consecutive_high_readings'],2)

if __name__=='__main__':unittest.main()
