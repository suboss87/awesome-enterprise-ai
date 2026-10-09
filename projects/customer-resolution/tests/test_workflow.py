"""Frozen business outcomes plus evidence and input-contract regression tests."""
import copy
import json
from pathlib import Path
import unittest
from enterprise_ai.catalog import load
from enterprise_ai.common import InputError, ReplayAI

PROJECT = Path(__file__).resolve().parents[1]
SLUG = PROJECT.name
WORKFLOW = load(SLUG)
CASES = json.loads((PROJECT / 'evaluation/cases.json').read_text())['cases']


class BusinessCases(unittest.TestCase):
    def test_input_is_not_mutated(self):
        data = json.loads((PROJECT / 'examples/input.json').read_text())
        original = copy.deepcopy(data)
        ai = ReplayAI(json.loads((PROJECT / 'examples/responses.json').read_text()))
        output = WORKFLOW.run(data, ai)
        self.assertEqual(data, original)
        self.assertTrue(output['human_review_required'])
        self.assertEqual(output['project'], SLUG)
        self.assertEqual(len(ai.calls), 1)

    def test_unknown_top_level_field_rejected_before_model(self):
        data = json.loads((PROJECT / 'examples/input.json').read_text())
        data['execute_now'] = True
        ai = ReplayAI([])
        with self.assertRaises(InputError):
            WORKFLOW.run(data, ai)
        self.assertEqual(ai.calls, [])


    def test_uncertain_tool_never_claims_completion(self):
        data = json.loads((PROJECT / 'examples/input.json').read_text())
        data['tool_state'] = 'uncertain'
        ai = ReplayAI(json.loads((PROJECT / 'examples/responses.json').read_text()))
        out = WORKFLOW.run(data, ai)
        self.assertEqual(out['handoff']['completed_actions'], [])
        self.assertEqual(out['actions'][0]['status'], 'blocked')
        self.assertFalse(out['actions'][0]['execution_performed'])

    def test_refund_cap_and_prior_refunds_both_constrain_amount(self):
        data = json.loads((PROJECT / 'examples/input.json').read_text())
        data['order']['refunded_cents'] = 4000
        data['policy']['max_refund_cents'] = 700
        ai = ReplayAI(json.loads((PROJECT / 'examples/responses.json').read_text()))
        self.assertEqual(WORKFLOW.run(data, ai)['actions'][0]['maximum_refund_cents'], 700)

    def test_over_refunded_record_rejected_before_model(self):
        data = json.loads((PROJECT / 'examples/input.json').read_text())
        data['order']['refunded_cents'] = 6000
        with self.assertRaises(InputError): WORKFLOW.run(data, ReplayAI([]))

    def test_message_order_binding_mismatch_rejected_before_model(self):
        data = json.loads((PROJECT / 'examples/input.json').read_text())
        data['message']['customer_ref'] = 'different-customer'
        ai = ReplayAI([])
        with self.assertRaises(InputError): WORKFLOW.run(data, ai)
        self.assertEqual(ai.calls, [])

    def test_currency_is_carried_into_proposal_and_metrics(self):
        data = json.loads((PROJECT / 'examples/input.json').read_text())
        data['order']['currency'] = 'EUR'
        ai = ReplayAI(json.loads((PROJECT / 'examples/responses.json').read_text()))
        output = WORKFLOW.run(data, ai)
        self.assertEqual(output['actions'][0]['currency'], 'EUR')
        self.assertEqual(output['metrics']['currency'], 'EUR')

    def test_invalid_currency_rejected_before_model(self):
        data = json.loads((PROJECT / 'examples/input.json').read_text())
        data['order']['currency'] = 'usd'
        ai = ReplayAI([])
        with self.assertRaises(InputError): WORKFLOW.run(data, ai)
        self.assertEqual(ai.calls, [])


def make_test(case):
    def test(self):
        ai = ReplayAI(copy.deepcopy(case['replay_responses']))
        if case['expected']['error']:
            with self.assertRaises(InputError):
                WORKFLOW.run(copy.deepcopy(case['input']), ai)
            return
        output = WORKFLOW.run(copy.deepcopy(case['input']), ai)
        self.assertEqual(ai.responses, [])
        for metric, expected in case['expected']['metrics'].items():
            self.assertEqual(output['metrics'][metric], expected, metric)
        codes = {finding['code'] for finding in output['findings']}
        for expected in case['expected']['findings']:
            self.assertIn(expected, codes)
        self.assertTrue(output['human_review_required'])
    return test


for case in CASES:
    setattr(BusinessCases, 'test_case_' + case['id'].replace('-', '_'), make_test(case))

if __name__ == '__main__':
    unittest.main()
