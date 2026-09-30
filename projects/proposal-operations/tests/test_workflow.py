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


    def test_expired_draft_is_removed_not_only_flagged(self):
        data = json.loads((PROJECT / 'examples/input.json').read_text())
        data['sources'][0]['valid_until'] = '2026-08-01'
        out = WORKFLOW.run(data, ReplayAI(json.loads((PROJECT / 'examples/responses.json').read_text())))
        self.assertEqual(out['matrix'][0]['draft'], '')
        self.assertEqual(out['matrix'][0]['invalid_sources'], {'doc-1': 'expired'})
        self.assertEqual(out['matrix'][0]['review_status'], 'unreviewed')

    def test_claimed_support_with_no_quote_rejected(self):
        data = json.loads((PROJECT / 'examples/input.json').read_text())
        responses = json.loads((PROJECT / 'examples/responses.json').read_text())
        responses[0]['answers'][0]['evidence'] = []
        with self.assertRaises(InputError): WORKFLOW.run(data, ReplayAI(responses))

    def test_duplicate_sources_rejected_before_model(self):
        data = json.loads((PROJECT / 'examples/input.json').read_text())
        data['sources'].append(copy.deepcopy(data['sources'][0]))
        with self.assertRaises(InputError): WORKFLOW.run(data, ReplayAI([]))


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
