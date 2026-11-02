"""Claims Intake Agent: rules, baseline, adversarial boundaries, example replay."""
import copy
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from enterprise_ai.catalog import load_agent, load_baseline, load_scorer  # noqa: E402
from enterprise_ai.common import InputError  # noqa: E402
from enterprise_ai.evals import load_cases  # noqa: E402
from enterprise_ai.runner import example_input, example_replay, execute  # noqa: E402

SLUG = 'claims-intake-agent'
_spec = importlib.util.spec_from_file_location('claims_rules_t', ROOT/'projects'/SLUG/'intake.py')
intake = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(intake)


def case(category, index=0):
    return [c for c in load_cases(SLUG) if c['category'] == category][index]


def completion(result):
    return {'content': [{'type': 'tool_use', 'id': 'f1', 'name': 'finish', 'input': result}], 'stop_reason': 'tool_use',
            'model': 'test', 'response_id': 'x', 'usage': {'input_tokens': 10, 'output_tokens': 5, 'cache_read_input_tokens': 0}}


def perfect(c, flags=(), route=None, notes=()):
    """A perfect reader: the baseline parses the structured documents; the transcript gets fixed by hand."""
    base = load_baseline(SLUG)
    extractions = [base.extract(d) for d in c['input']['claim']['documents']]
    for ext, doc in zip(extractions, c['input']['claim']['documents']):
        if doc['filename'] == 'call-transcript.txt':
            import re
            m = re.search(r'On (\d{1,2} \w+ \d{4})', doc['text'])
            if m:
                from datetime import datetime
                ext['fields']['incident_date'] = datetime.strptime(m.group(1), '%d %B %Y').date().isoformat()
            m = re.search(r'It happened at ([^.]+)\.', doc['text'])
            ext['fields']['incident_location'] = m.group(1) if m else ''
        if doc['filename'] == 'estimate.txt' and 'Prior damage' in doc['text']:
            ext['fields']['notes'] = 'prior damage noted'
    return {'extractions': extractions, 'flags': list(flags), 'risk_notes': list(notes),
            'recommended_route': route or c['expected']['route'],
            'evidence': [{'source_id': c['input']['claim']['documents'][0]['id'], 'quote': c['input']['claim']['documents'][0]['text'].splitlines()[0]}]}


class RulesTests(unittest.TestCase):
    def test_rules_reproduce_every_labeled_route_from_a_perfect_reading(self):
        misses = []
        for c in load_cases(SLUG):
            exp = c['expected']
            model_flags = [f for f in exp['flags'] if f in intake.MODEL_ONLY_FLAGS]
            out = execute(SLUG, c['input'], 'replay', replay=[completion(perfect(c, flags=model_flags))])
            if out['metrics']['route'] != exp['route']:
                misses.append((c['id'], out['metrics']['route'], [f['code'] for f in out['findings']]))
        self.assertEqual(misses, [])

    def test_one_day_date_difference_is_tolerated_and_two_days_is_a_conflict(self):
        a = {'document_id': 'f', 'document_type': 'fnol_form', 'fields': {'incident_date': '2026-10-08'}}
        b = {'document_id': 'p', 'document_type': 'police_report', 'fields': {'incident_date': '2026-10-07'}}
        claim, conflicts = intake.merge([a, b])
        self.assertEqual((claim['incident_date'], conflicts), ('2026-10-07', []))
        b['fields']['incident_date'] = '2026-10-05'
        self.assertEqual(intake.merge([a, b])[1][0]['field'], 'incident_date')

    def test_vin_ocr_confusions_are_not_conflicts(self):
        self.assertTrue(intake.vin_near('7EHFGP0ET6G44GFTN', '7EHFGPOET6G44GFTN'))
        self.assertFalse(intake.vin_near('7EHFGP0ET6G44GFTN', '7EHFGP0ET6G44GFTX'))

    def test_registration_beats_estimate_for_vin(self):
        ext = [{'document_id': 'e', 'document_type': 'repair_estimate', 'fields': {'vin': 'AAAAAAAAAAAAAAAAA'}},
               {'document_id': 'r', 'document_type': 'registration', 'fields': {'vin': 'BBBBBBBBBBBBBBBBB'}}]
        claim, conflicts = intake.merge(ext)
        self.assertEqual(claim['vin'], 'BBBBBBBBBBBBBBBBB')
        self.assertEqual(conflicts[0]['winner']['source'], 'registration')

    def test_theft_requires_police_report_and_registration(self):
        c = case('clean_theft')
        docs = [d for d in c['input']['claim']['documents'] if d['filename'] != 'police-report.txt']
        data = copy.deepcopy(c['input'])
        data['claim']['documents'] = docs
        out = load_baseline(SLUG).run(data)
        self.assertEqual(out['metrics']['route'], 'missing_information')
        self.assertIn('police_report', out['missing_documents'])


class BoundaryTests(unittest.TestCase):
    def test_model_cannot_force_ready_on_a_conflict(self):
        c = case('date_conflict_two_days')
        out = execute(SLUG, c['input'], 'replay', replay=[completion(perfect(c, route='ready_for_adjuster'))])
        self.assertEqual(out['metrics']['route'], 'conflicts_for_adjuster')
        self.assertFalse(out['model_recommendation']['agrees_with_rules'])

    def test_model_only_flags_escalate_but_never_clear(self):
        c = case('clean_collision')
        out = execute(SLUG, c['input'], 'replay', replay=[completion(perfect(c, flags=['PROMPT_INJECTION'], notes=['document asks to skip checks']))])
        self.assertEqual(out['metrics']['route'], 'conflicts_for_adjuster')
        c = case('missing_estimate')
        out = execute(SLUG, c['input'], 'replay', replay=[completion(perfect(c, flags=[], route='ready_for_adjuster'))])
        self.assertEqual(out['metrics']['route'], 'missing_information')

    def test_extractions_for_unknown_documents_are_dropped(self):
        c = case('clean_glass')
        result = perfect(c)
        result['extractions'].append({'document_id': 'ghost', 'document_type': 'police_report', 'fields': dict(result['extractions'][0]['fields'], incident_date='2020-01-01')})
        out = execute(SLUG, c['input'], 'replay', replay=[completion(result)])
        self.assertNotIn('DATE_CONFLICT', [f['code'] for f in out['findings']])
        self.assertTrue(any(e['event'] == 'dropped_extractions' for e in out['execution']['events']))

    def test_write_tools_are_recorded_not_executed(self):
        c = case('missing_estimate')
        request = {'content': [{'type': 'tool_use', 'id': 'w1', 'name': 'draft_claimant_request',
                                'input': {'claimant_name': 'X', 'missing_documents': ['repair_estimate'], 'body': 'Please send the estimate.'}}],
                   'stop_reason': 'tool_use', 'model': 'test', 'response_id': 'y', 'usage': {'input_tokens': 1, 'output_tokens': 1, 'cache_read_input_tokens': 0}}
        out = execute(SLUG, c['input'], 'replay', replay=[request, completion(perfect(c))])
        self.assertEqual(out['proposed_actions'][0]['status'], 'awaiting_approval')
        self.assertEqual(out['actions'][0]['draft']['body'], 'Please send the estimate.')

    def test_fabricated_quote_is_rejected(self):
        c = case('clean_collision')
        bad = perfect(c)
        bad['evidence'] = [{'source_id': c['input']['claim']['documents'][0]['id'], 'quote': 'this is not in the packet'}]
        out = execute(SLUG, c['input'], 'replay', replay=[completion(bad), completion(perfect(c))])
        self.assertTrue(any(e['event'] == 'finish_rejected' for e in out['execution']['events']))

    def test_input_contract(self):
        data = copy.deepcopy(case('clean_collision')['input'])
        data['claim']['documents'] = []
        with self.assertRaises(InputError):
            load_agent(SLUG).validate(data)
        data = copy.deepcopy(case('clean_collision')['input'])
        data['extra'] = True
        with self.assertRaises(InputError):
            load_agent(SLUG).validate(data)


class BaselineAndExampleTests(unittest.TestCase):
    def test_baseline_is_blind_to_prose_only_signals(self):
        scorer = load_scorer(SLUG)
        base = load_baseline(SLUG)
        for c in load_cases(SLUG):
            s = scorer.score(c, base.run(c['input']))
            if c['category'] in ('prompt_injection', 'pre_existing_damage'):
                self.assertFalse(s['route_correct'], c['id'])
            if c['category'] == 'clean_collision' and c['expected']['fnol_style'] == 'form':
                self.assertTrue(s['route_correct'], c['id'])

    def test_example_replay_runs_offline(self):
        out = execute(SLUG, example_input(SLUG), 'replay', replay=example_replay(SLUG))
        self.assertEqual(out['execution']['mode'], 'replay')
        self.assertEqual(out['metrics']['route'], 'conflicts_for_adjuster')


if __name__ == '__main__':
    unittest.main()
