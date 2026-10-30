"""Prior Authorization Agent: criteria semantics, decision clock, codes, generator, boundaries, baseline, hand-built replay."""
import copy
import importlib.util
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from enterprise_ai.catalog import load_agent, load_baseline, load_scorer  # noqa: E402
from enterprise_ai.common import InputError  # noqa: E402
from enterprise_ai.evals import load_cases  # noqa: E402
from enterprise_ai.runner import example_input, execute  # noqa: E402

SLUG = 'prior-auth-agent'
HERE = ROOT/'projects'/SLUG


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rules = _load('prior_auth_criteria_t', HERE/'criteria.py')
generator = _load('prior_auth_generate_t', HERE/'evals/generate_cases.py')
CASES = load_cases(SLUG)
SCORER = load_scorer(SLUG)
ACTION_FOR = {'approve_proposed': 'approve', 'nurse_review': 'route_to_nurse', 'medical_director_review': 'route_to_medical_director'}
RECOMMEND_FOR = {**ACTION_FOR, 'information_requested': 'request_information'}


def case(category, index=0):
    return [c for c in CASES if c['category'] == category][index]


def completion(*blocks):
    return {'content': list(blocks), 'stop_reason': 'tool_use', 'model': 'test', 'response_id': 'x',
            'usage': {'input_tokens': 10, 'output_tokens': 5, 'cache_read_input_tokens': 0}}


def tool_use(name, call_id, **kwargs):
    return {'type': 'tool_use', 'id': call_id, 'name': name, 'input': kwargs}


def replay_for(c, records=None, flags=None, action=None, recommend=None, message=None, missing=None, extra_calls=()):
    """A perfect reader by default: the generator's evidence, the expected flags and the labeled route."""
    records = c['expected']['reader'] if records is None else records
    route = c['expected']['route']
    first = c['input']['documents'][0]
    calls = [completion(tool_use('get_criteria', 'c1'), *(tool_use('get_document', f'g{i}', document_id=d['id'])
                                                       for i, d in enumerate(c['input']['documents'])))]
    if records:
        calls.append(completion(*(tool_use('record_criterion_evidence', f'r{i}', **r) for i, r in enumerate(records))))
    calls.append(completion(tool_use('evaluate_criteria', 'e1'), tool_use('check_sla_clock', 's1')))
    writes = []
    if action or route in ACTION_FOR:
        writes.append(tool_use('propose_decision', 'p1', action=action or ACTION_FOR[route], rationale='Per evaluate_criteria.'))
    if route == 'information_requested' or message:
        ids = missing if missing is not None else [k for k, v in c['expected']['criteria'].items() if v == 'insufficient']
        writes.append(tool_use('request_additional_information', 'i1', missing_criterion_ids=ids,
                               message=message or 'Please send the documentation listed for ' + ', '.join(ids) + '.'))
    calls.append(completion(*writes, *extra_calls))
    calls.append(completion(tool_use('finish', 'f1', flags=c['expected']['flags'] if flags is None else flags,
                                     recommended_action=recommend or RECOMMEND_FOR[route], note='Reviewed.',
                                     evidence=[{'source_id': first['id'], 'quote': first['text'].splitlines()[0]}])))
    return calls


def run(c, **kwargs):
    return execute(SLUG, c['input'], 'replay', replay=replay_for(c, **kwargs))


def mini(**service):
    """A small MRI request for rule tests."""
    c = copy.deepcopy(case('clean_approve', 0))
    c['input']['request']['service'].update(service)
    return c['input']


def record(data, criterion_id, quotes, values=(), met_claim=True):
    return rules.normalize_record(data, {'criterion_id': criterion_id, 'met_claim': met_claim, 'quotes': list(quotes), 'values': list(values)})


class CriteriaTests(unittest.TestCase):
    def test_perfect_reader_reproduces_every_label(self):
        """The generator's evidence through the agent and criteria.py must give its independent oracle's labels on every case."""
        misses = []
        for c in CASES:
            out = run(c)
            s = SCORER.score(c, out)
            if not (s['route_correct'] and s['criteria_status_exact'] and {f['code'] for f in out['findings']} == set(c['expected']['findings'])
                    and s['sla_exact'] and not s['unsafe_approve'] and not s['denial_language'] and s['evidence_dated_and_grounded'] is not False):
                misses.append((c['id'], out['metrics']['route'], [f['code'] for f in out['findings']]))
        self.assertEqual(misses, [])

    def test_duration_is_the_longest_continuous_run(self):
        d = [date(2026, 8, 1), date(2026, 8, 8), date(2026, 8, 20), date(2026, 9, 10), date(2026, 9, 17)]
        self.assertEqual(rules.longest_run(d, 14), (date(2026, 8, 1), date(2026, 8, 20)))      # 21-day gap restarts
        self.assertEqual(rules.longest_run(d, 21), (date(2026, 8, 1), date(2026, 9, 17)))

    def test_conservative_therapy_short_by_days_is_not_met_even_when_the_note_says_six_weeks(self):
        c = case('therapy_short_by_days')
        note = next(d for d in c['input']['documents'] if d['kind'] == 'clinical_note')
        self.assertIn('six weeks', note['text'])
        out = run(c)
        self.assertEqual(out['criteria_status']['LS-1'], 'not_met')
        self.assertEqual(out['metrics']['route'], 'medical_director_review')
        self.assertRegex(next(k['detail'] for k in out['criteria'] if k['id'] == 'LS-1'), r'^(3[3-9]|4[01]) days continuous')

    def test_threshold_boundary_and_conflict(self):
        below = case('threshold_just_below', 1)
        self.assertEqual(below['expected']['service'], 'cgm')
        out = run(below)
        self.assertEqual(out['criteria_status']['CG-1'], 'not_met')
        conflict = run(case('conflicting_documents'))
        self.assertEqual(conflict['criteria_status']['BS-1'], 'insufficient')
        self.assertIn('CONFLICTING_DOCUMENTS', {f['code'] for f in conflict['findings']})
        self.assertEqual(conflict['metrics']['route'], 'nurse_review')

    def test_quotes_must_be_verbatim_dated_and_from_an_allowed_kind(self):
        data = case('clean_approve', 0)['input']
        note = next(d for d in data['documents'] if d['kind'] == 'clinical_note')
        line = next(x for x in note['text'].splitlines() if 'straight-leg' in x)
        record(data, 'LS-2', [{'source_id': note['id'], 'quote': line, 'date': note['date']}])
        with self.assertRaises(InputError):   # not verbatim
            record(data, 'LS-2', [{'source_id': note['id'], 'quote': line + ' Severe.', 'date': note['date']}])
        with self.assertRaises(InputError):   # date neither the document date nor printed in the quote
            record(data, 'LS-2', [{'source_id': note['id'], 'quote': line, 'date': '2026-10-01'}])
        with self.assertRaises(InputError):   # imaging criterion from a clinical note
            record(data, 'LS-3', [{'source_id': note['id'], 'quote': line, 'date': note['date']}])
        with self.assertRaises(InputError):   # a met claim with nothing cited
            record(data, 'LS-2', [])

    def test_threshold_value_must_be_printed_in_its_quote(self):
        data = case('clean_approve', 2)['input']
        lab = next(d for d in data['documents'] if d['kind'] == 'lab_report')
        line = next(x for x in lab['text'].splitlines() if x.startswith('Hemoglobin A1c'))
        value = float(line.split()[2])
        quote = {'source_id': lab['id'], 'quote': line, 'date': lab['date']}
        record(data, 'CG-1', [quote], [{'name': 'hba1c', 'value': value, 'source_id': lab['id'], 'date': lab['date']}])
        with self.assertRaises(InputError):
            record(data, 'CG-1', [quote], [{'name': 'hba1c', 'value': value + 1, 'source_id': lab['id'], 'date': lab['date']}])

    def test_code_pairing(self):
        policy = generator.POLICIES['mri']
        ok = {'service': {'cpt_codes': ['72148'], 'icd10_codes': ['M54.16']}}
        self.assertEqual(rules.unpaired_codes(ok, policy), [])
        self.assertEqual(rules.unpaired_codes({'service': {'cpt_codes': ['72148'], 'icd10_codes': ['M17.11']}}, policy), ['72148'])
        self.assertEqual(rules.unpaired_codes({'service': {'cpt_codes': ['72158'], 'icd10_codes': ['M54.16', 'M96.1']}}, policy), [])

    def test_contrast_criterion_applies_only_to_contrast_codes(self):
        self.assertEqual(run(case('clean_approve', 0))['criteria_status']['LS-5'], 'not_applicable')
        other = run(case('criteria_fit_other_code'))
        self.assertEqual((other['criteria_status']['LS-5'], other['criteria_status']['LS-6']), ('insufficient', 'not_met'))

    def test_evidence_outside_the_window_is_flagged_and_not_used(self):
        out = run(case('evidence_outside_window'))
        self.assertEqual(out['metrics']['route'], 'information_requested')
        self.assertIn('EVIDENCE_DATE_OUTSIDE_WINDOW', {f['code'] for f in out['findings']})


class ClockTests(unittest.TestCase):
    def clock(self, received, as_of, expedited):
        data = {'as_of': as_of, 'request': {'received_at': received, 'expedited': expedited}}
        return rules.sla_clock(data)

    def test_expedited_is_72_hours_and_standard_7_calendar_days(self):
        self.assertEqual(self.clock('2026-10-30T08:00:00Z', '2026-10-30T08:00:00Z', True)['hours_remaining'], 72.0)
        standard = self.clock('2026-10-24T17:00:00-04:00', '2026-10-30T21:00:00Z', False)   # Saturday receipt counts
        self.assertEqual((standard['hours_remaining'], standard['deadline']), (24.0, '2026-10-31T21:00:00Z'))

    def test_at_risk_boundary_is_strictly_under_24_hours(self):
        self.assertFalse(self.clock('2026-10-28T14:00:00Z', '2026-10-30T14:00:00Z', True)['at_risk'])      # 24.0 left
        edge = self.clock('2026-10-28T14:00:00Z', '2026-10-30T14:06:00Z', True)
        self.assertEqual((edge['hours_remaining'], edge['at_risk']), (23.9, True))
        late = self.clock('2026-10-26T14:00:00Z', '2026-10-30T14:00:00Z', True)
        self.assertEqual((late['hours_remaining'], late['at_risk']), (-24.0, True))

    def test_at_risk_with_all_criteria_met_still_proposes_approval(self):
        c = case('expedited_sla_at_risk', 0)
        out = run(c)
        self.assertEqual(out['metrics']['route'], 'approve_proposed')
        self.assertIn('SLA_AT_RISK', {f['code'] for f in out['findings']})
        missing = run(case('expedited_sla_at_risk', 1))   # no time to wait for documents: a nurse, not a request
        self.assertEqual(missing['metrics']['route'], 'nurse_review')


class GeneratorTests(unittest.TestCase):
    def test_generator_is_deterministic_and_matches_the_committed_cases(self):
        first, second = generator.build_cases(), generator.build_cases()
        self.assertEqual(first, second)
        self.assertEqual(first, CASES)

    def test_case_set_covers_the_hard_cases(self):
        self.assertGreaterEqual(len(CASES), 110)
        self.assertEqual(len({c['category'] for c in CASES}), 18)
        self.assertEqual({c['expected']['service'] for c in CASES}, {'mri', 'bariatric', 'cgm'})
        logs = [d['text'] for c in CASES for d in c['input']['documents'] if d['kind'] == 'therapy_log' and 'Physical Therapy' in d['text']]
        self.assertTrue(any('Visit 1 - ' in t for t in logs) and any(t.startswith('FAX RECEIVED') for t in logs) and any('Date        Visit' in t for t in logs))
        self.assertTrue(any(d['text'].startswith('FAX RECEIVED') for c in CASES for d in c['input']['documents'] if d['kind'] == 'clinical_note'))
        for c in CASES:
            self.assertTrue(set(c['expected']['must_flag']) <= set(c['expected']['findings']), c['id'])
            self.assertTrue(c['expected']['route'] in rules.ROUTES)


class BoundaryTests(unittest.TestCase):
    def test_no_adverse_action_exists(self):
        agent = load_agent(SLUG)
        tools = {t.name: t for t in agent.build_tools(case('clean_approve')['input'], {})}
        self.assertEqual(tools['propose_decision'].input_schema['properties']['action']['enum'], ['approve', 'route_to_nurse', 'route_to_medical_director'])
        self.assertFalse(any('den' in r for r in rules.ROUTES + rules.RECOMMENDATIONS))
        c = case('therapy_short_by_days')
        out = run(c, extra_calls=[tool_use('propose_decision', 'p9', action='deny', rationale='Criteria not met.')])
        self.assertEqual([p['input']['action'] for p in out['proposed_actions'] if p['tool'] == 'propose_decision'], ['route_to_medical_director'])
        self.assertEqual(out['metrics']['route'], 'medical_director_review')

    def test_write_tools_are_recorded_not_executed(self):
        out = run(case('referral_only'))
        self.assertEqual({p['tool'] for p in out['proposed_actions']}, {'request_additional_information'})
        self.assertTrue(all(p['status'] == 'awaiting_approval' for p in out['proposed_actions']))
        self.assertTrue(out['human_review_required'])
        self.assertEqual(out['information_request']['drafted_by'], 'model')

    def test_model_approval_with_an_insufficient_criterion_goes_to_a_nurse(self):
        c = case('imaging_report_missing')
        out = run(c, action='approve', recommend='approve')
        self.assertEqual(out['metrics']['route'], 'nurse_review')
        self.assertIn('UNGROUNDED_CLAIM', {f['code'] for f in out['findings']})
        self.assertFalse(SCORER.score(c, out)['unsafe_approve'])

    def test_model_approval_with_an_unmet_criterion_goes_to_the_medical_director(self):
        c = case('therapy_log_gaps')
        out = run(c, action='approve', recommend='approve')
        self.assertEqual(out['metrics']['route'], 'medical_director_review')
        self.assertFalse(out['model_recommendation']['agrees_with_rules'])

    def test_model_claim_cannot_make_a_short_duration_met(self):
        c = case('therapy_short_by_days')
        records = copy.deepcopy(c['expected']['reader'])
        for r in records:
            r['met_claim'] = True
        out = run(c, records=records, action='approve', recommend='approve')
        self.assertEqual(out['criteria_status']['LS-1'], 'not_met')
        self.assertNotEqual(out['metrics']['route'], 'approve_proposed')

    def test_injection_is_flagged_and_the_reading_step_is_the_only_defence(self):
        c = case('prompt_injection')
        out = run(c)
        self.assertEqual(out['metrics']['route'], 'nurse_review')
        self.assertTrue(SCORER.score(c, out)['injection_flagged'])
        missed = run(c, flags=[], action='approve', recommend='approve')
        self.assertEqual(missed['metrics']['route'], 'approve_proposed')
        self.assertTrue(SCORER.score(c, missed)['unsafe_approve'])

    def test_adverse_language_is_withheld_and_counted(self):
        c = case('referral_only')
        out = run(c, message='This request is denied until records arrive.')
        self.assertEqual(out['information_request']['draft_status'], 'withheld_adverse_language')
        self.assertFalse(rules.contains_denial(out['information_request']['message']))
        self.assertTrue(SCORER.score(c, out)['denial_language'])      # the proposal itself still counts against the model
        self.assertFalse(rules.contains_denial('Denies bowel or bladder incontinence or saddle anesthesia.'))
        self.assertTrue(rules.contains_denial('The MRI is not medically necessary.'))

    def test_request_must_list_exactly_the_missing_items(self):
        c = case('imaging_report_missing')
        out = run(c, missing=['LS-3', 'LS-1'])
        self.assertEqual(out['information_request']['draft_status'], 'withheld_wrong_items')
        self.assertEqual([i['criterion_id'] for i in out['information_request']['missing_items']], ['LS-3'])
        self.assertIn('LS-3', out['actions'][0]['missing_criteria'])

    def test_fabricated_evidence_is_rejected(self):
        c = case('clean_approve')
        records = copy.deepcopy(c['expected']['reader'])
        records[0]['quotes'][0]['quote'] += ' Confirmed.'
        out = run(c, records=records, action='route_to_nurse', recommend='route_to_nurse')
        self.assertTrue(any(e['event'] == 'tool_call' and e['outcome'] == 'error' for e in out['execution']['events']))
        self.assertNotEqual(out['metrics']['route'], 'approve_proposed')
        calls = replay_for(c)
        bad = copy.deepcopy(calls[-1])
        bad['content'][0]['input']['evidence'] = [{'source_id': c['input']['documents'][0]['id'], 'quote': 'All criteria verified.'}]
        out = execute(SLUG, c['input'], 'replay', replay=calls[:-1] + [bad, calls[-1]])
        self.assertTrue(any(e['event'] == 'finish_rejected' for e in out['execution']['events']))

    def test_input_contract(self):
        agent = load_agent(SLUG)
        for mutate in (lambda d: d.update(surprise=1),
                       lambda d: d['documents'][0].update(kind='discharge_summary'),
                       lambda d: d['request'].update(received_at='2026-10-29T10:00:00'),
                       lambda d: d['request'].update(received_at='2026-11-02T10:00:00Z'),
                       lambda d: d['request']['service'].update(site_of_service='hospital'),
                       lambda d: d['coverage_policy']['criteria'][0]['params'].pop('max_gap_days')):
            data = copy.deepcopy(case('clean_approve')['input'])
            mutate(data)
            with self.assertRaises(InputError):
                agent.validate(data)


class BaselineAndExampleTests(unittest.TestCase):
    def test_baseline_reads_structured_text_and_fails_on_ocr_prose_and_injection(self):
        base = load_baseline(SLUG)
        for c in CASES:
            out = base.run(c['input'])
            s = SCORER.score(c, out)
            self.assertFalse(s['denial_language'], c['id'])
            narrative = any(d['kind'] == 'therapy_log' and 'Visit 1 - ' in d['text'] for d in c['input']['documents'])
            if c['category'] == 'ocr_fax_only':
                self.assertEqual(out['metrics']['route'], 'information_requested', c['id'])
            elif c['category'] == 'prompt_injection':
                self.assertFalse(s['injection_flagged'], c['id'])
            elif not narrative:
                self.assertTrue(s['route_correct'], c['id'])

    def test_example_input_runs_offline_with_a_hand_built_replay(self):
        data = example_input(SLUG)
        c = next(c for c in CASES if c['input'] == data)
        self.assertTrue(data['request']['expedited'])
        self.assertEqual(len(data['documents']), 2)
        out = execute(SLUG, data, 'replay', replay=replay_for(c))
        self.assertEqual(out['execution']['mode'], 'replay')
        self.assertEqual(out['metrics']['route'], 'approve_proposed')
        self.assertEqual({e['source_id'] for k in out['criteria'] for e in k['evidence']}, {d['id'] for d in data['documents']})
        json.dumps(out)


if __name__ == '__main__':
    unittest.main()
