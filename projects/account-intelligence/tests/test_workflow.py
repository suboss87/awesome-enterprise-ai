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


    def test_meeting_proposal_does_not_change_crm_or_forecast(self):
        data = json.loads((PROJECT / 'examples/input.json').read_text())
        out = WORKFLOW.run(data, ReplayAI(json.loads((PROJECT / 'examples/responses.json').read_text())))
        self.assertEqual(out['opportunities'][0]['close_date'], '2026-10-15')
        self.assertIsNone(out['forecast_probability'])
        self.assertTrue(all(not o['crm_changed'] for o in out['observations']))

    def test_duplicate_observations_rejected(self):
        data = json.loads((PROJECT / 'examples/input.json').read_text())
        responses = json.loads((PROJECT / 'examples/responses.json').read_text())
        responses[0]['observations'].append(copy.deepcopy(responses[0]['observations'][0]))
        with self.assertRaises(InputError): WORKFLOW.run(data, ReplayAI(responses))

    def test_future_meeting_rejected_before_model(self):
        data = json.loads((PROJECT / 'examples/input.json').read_text())
        data['meetings'][0]['date'] = '2027-01-01'
        with self.assertRaises(InputError): WORKFLOW.run(data, ReplayAI([]))


    def observation_case(self, note, quote=None, kind='blocker', proposed_date=''):
        data = json.loads((PROJECT / 'examples/input.json').read_text())
        data['meetings'][0]['text'] = note
        other = copy.deepcopy(data['opportunities'][0])
        other['id'] = 'opp-2'
        data['opportunities'].append(other)
        response = {'observations': [{'opportunity_id': 'opp-1', 'kind': kind,
            'proposed_date': proposed_date, 'evidence': [{'source_id': 'meeting-1',
            'quote': quote if quote is not None else note}]}]}
        return data, [response]

    def test_unnamed_meeting_cannot_be_assigned_to_either_opportunity(self):
        data, responses = self.observation_case('Security review remains a blocker.')
        for target in ('opp-1', 'opp-2'):
            with self.subTest(target=target):
                responses[0]['observations'][0]['opportunity_id'] = target
                with self.assertRaises(InputError):
                    WORKFLOW.run(data, ReplayAI(responses))

    def test_single_opportunity_does_not_authorize_unnamed_meeting(self):
        data, responses = self.observation_case('Security review remains a blocker.')
        data['opportunities'] = data['opportunities'][:1]
        with self.assertRaises(InputError): WORKFLOW.run(data, ReplayAI(responses))

    def test_multiple_ids_in_quote_are_ambiguous(self):
        data, responses = self.observation_case('For opp-1 and opp-2, security review remains a blocker.')
        with self.assertRaises(InputError): WORKFLOW.run(data, ReplayAI(responses))

    def test_unbound_quote_in_multiple_opportunity_meeting_rejected(self):
        data, responses = self.observation_case(
            'Discussed opp-1 and opp-2. Security review remains a blocker.',
            'Security review remains a blocker.')
        with self.assertRaises(InputError): WORKFLOW.run(data, ReplayAI(responses))

    def test_exact_quote_can_disambiguate_multiple_opportunity_meeting(self):
        quote = 'For opp-1, security review remains a blocker.'
        data, responses = self.observation_case(quote + ' For opp-2, the review is complete.', quote)
        out = WORKFLOW.run(data, ReplayAI(responses))
        self.assertEqual(out['observations'][0]['opportunity_id'], 'opp-1')

    def test_single_explicit_meeting_id_binds_unlabelled_quote(self):
        data, responses = self.observation_case(
            'Discussed opp-1. Security review remains a blocker.',
            'Security review remains a blocker.')
        out = WORKFLOW.run(data, ReplayAI(responses))
        self.assertEqual(out['observations'][0]['opportunity_id'], 'opp-1')

    def test_opportunity_id_prefix_cannot_establish_identity(self):
        for wrong_id in ('opp-10', 'xopp-1', 'opp-1-extra'):
            with self.subTest(wrong_id=wrong_id):
                data, responses = self.observation_case(f'For {wrong_id}, security review remains a blocker.')
                with self.assertRaises(InputError): WORKFLOW.run(data, ReplayAI(responses))

    def test_date_must_be_complete_token(self):
        for invalid in ('2026-11-010', '12026-11-01', 'ref-2026-11-01',
                        '2026-11-01-extra', '2026-11-01T12:00:00',
                        '2026-11-01 12:00:00', '2026-11-01\t12:00:00',
                        '2026-11-01 9:30', '2026-11-01  12:00:00+05:30'):
            with self.subTest(token=invalid):
                data, responses = self.observation_case(
                    f'For opp-1, the requested date is {invalid}.',
                    kind='date_change', proposed_date='2026-11-01')
                with self.assertRaises(InputError): WORKFLOW.run(data, ReplayAI(responses))

    def test_date_allows_sentence_and_parenthesis_punctuation(self):
        for token in ('2026-11-01.', '(2026-11-01)', '2026-11-01,',
                      '2026-11-01 after review', '2026-11-01\tconfirmed'):
            with self.subTest(token=token):
                data, responses = self.observation_case(
                    f'For opp-1, the requested date is {token}',
                    kind='date_change', proposed_date='2026-11-01')
                out = WORKFLOW.run(data, ReplayAI(responses))
                self.assertEqual(out['observations'][0]['proposed_date'], '2026-11-01')


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
