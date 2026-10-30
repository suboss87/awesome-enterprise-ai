"""Lease Abstraction Agent: date arithmetic, precedence, generator, baseline, write boundary, grounding, injection, replay."""
import copy
import importlib.util
import json
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from enterprise_ai.agent import Trace  # noqa: E402
from enterprise_ai.common import InputError  # noqa: E402
from enterprise_ai.llm import ReplayProvider  # noqa: E402

SLUG = 'lease-abstraction-agent'
PROJECT = ROOT/'projects'/SLUG


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent = _load('lease_agent_t', PROJECT/'agent.py')
rules = agent.abstraction
baseline = _load('lease_baseline_t', PROJECT/'baseline.py')
scorer = _load('lease_score_t', PROJECT/'evals/score.py')
generator = _load('lease_generator_t', PROJECT/'evals/generate_cases.py')
CASES = [json.loads(line) for line in (PROJECT/'evals/cases.jsonl').read_text().splitlines() if line.strip()]
LABELED_CODES = {'DATE_CONFLICT_RESOLVED_BY_AMENDMENT', 'FIELD_AMENDED', 'UNRESOLVED_CONFLICT', 'MISSING_FIELD', 'NOTICE_WINDOW_PASSED',
                 'NOTICE_WINDOW_WITHIN_HORIZON', 'ESCALATION_TYPE_NOT_ALLOWED', 'CAM_CAP_MISSING', 'PROMPT_INJECTION', 'UNGROUNDED_FIELD', 'INVALID_FIELD'}


def case(category, index=0):
    return [c for c in CASES if c['category'] == category][index]


def completion(*blocks):
    return {'content': list(blocks), 'stop_reason': 'tool_use', 'model': 'test', 'response_id': 'x',
            'usage': {'input_tokens': 10, 'output_tokens': 5, 'cache_read_input_tokens': 0}}


def tool_use(name, **kwargs):
    return {'type': 'tool_use', 'id': f'call_{name}_{len(str(kwargs))}', 'name': name, 'input': kwargs}


def statements(c):
    return copy.deepcopy(c['expected']['reference_statements'])


def finish_result(c, flags=None, route=None, evidence=None):
    exp = c['expected']
    doc = next((d for d in c['input']['lease']['documents'] if exp['injection'] and exp['injection'] in d['text']), None)
    first = exp['reference_statements'][0]
    quote = {'source_id': doc['id'], 'quote': exp['injection']} if doc else {'source_id': first['document_id'], 'quote': first['quote']}
    return {'flags': (['PROMPT_INJECTION'] if exp['injection'] else []) if flags is None else flags,
            'recommended_route': route or exp['route'], 'rationale': 'Per the documents.', 'evidence': [quote] if evidence is None else evidence}


def run(c, completions, data=None):
    trace = Trace(SLUG, 'replay')
    out = agent.run(copy.deepcopy(data or c['input']), ReplayProvider(completions), trace)
    out['events'] = trace.events
    return out


def run_perfect(c, stated=None, extra=(), **finish):
    """A perfect reader: record the reference statements, then finish."""
    record = completion(tool_use('record_abstract', statements=statements(c) if stated is None else stated))
    return run(c, [record, *extra, completion(tool_use('finish', **finish_result(c, **finish)))])


class DateArithmeticTests(unittest.TestCase):
    def test_month_end_clamps_and_leap_years(self):
        self.assertEqual(rules.add_months(date(2024, 1, 31), 1), date(2024, 2, 29))
        self.assertEqual(rules.add_months(date(2023, 1, 31), 1), date(2023, 2, 28))
        self.assertEqual(rules.add_months(date(2026, 3, 31), -1), date(2026, 2, 28))
        self.assertEqual(rules.term_end(date(2026, 2, 1), 60), date(2031, 1, 31))
        self.assertEqual(rules.term_end(date(2024, 1, 31), 36), date(2027, 1, 30))
        self.assertEqual(rules.term_end(date(2023, 8, 31), 54), date(2028, 2, 28))
        self.assertEqual(rules.months_between(date(2026, 2, 1), date(2031, 1, 31)), 60)
        self.assertIsNone(rules.months_between(date(2026, 2, 1), date(2031, 1, 15)))

    def test_notice_windows_in_months_and_days(self):
        self.assertEqual(rules.before(date(2031, 1, 31), 12, 'months'), date(2030, 1, 31))
        self.assertEqual(rules.before(date(2031, 1, 31), 9, 'months'), date(2030, 4, 30))
        self.assertEqual(rules.before(date(2031, 1, 31), 270, 'days'), date(2030, 5, 6))
        fields = {'renewal_option': {'parsed': rules.parse_value('renewal_option', '1 x 5 years, notice 180 to 365 days, rent fmv')}}
        register = rules.critical_dates(fields, date(2027, 6, 30), [], date(2026, 10, 30), generator.RULES)
        by_kind = {e['kind']: e for e in register}
        self.assertEqual(by_kind['renewal_notice_opens']['date'], '2026-06-30')
        self.assertEqual(by_kind['renewal_notice_deadline']['date'], '2027-01-01')
        self.assertEqual(by_kind['renewal_notice_deadline']['status'], 'in_horizon')
        self.assertEqual(by_kind['renewal_notice_deadline']['alert_date'], '2026-10-03')

    def test_rent_basis_and_escalation_are_computed_in_cents(self):
        self.assertEqual(rules.monthly({'amount': Decimal('30.00'), 'basis': 'psf annual'}, 12400), Decimal('31000.00'))
        self.assertEqual(rules.monthly({'amount': Decimal('150000'), 'basis': 'annual'}, None), Decimal('12500.00'))
        self.assertIsNone(rules.monthly({'amount': Decimal('30.00'), 'basis': 'psf annual'}, None))
        self.assertEqual(rules.parse_value('rentable_area', '1,152 sq m')['sqft'], 12400)
        self.assertEqual(rules.parse_value('holdover', '1.5x')['pct'], Decimal('150'))
        for field, value in (('term_months', 'five years'), ('base_rent', '12500'), ('cam', 'triple net'), ('renewal_option', '1 x 5 years'),
                             ('commencement_date', 'March 1, 2026'), ('escalation', 'fixed_pct 3')):
            with self.assertRaises(InputError):
                rules.parse_value(field, value)


class PrecedenceTests(unittest.TestCase):
    def test_perfect_reader_reproduces_every_label(self):
        """If the model reads perfectly, abstraction.py alone produces every labeled route, date, rent, register entry, code and conflict."""
        misses = []
        for c in CASES:
            exp = c['expected']
            out = run_perfect(c)
            codes = {f['code'] for f in out['findings']} & LABELED_CODES
            horizon = sorted([e['kind'], e['date']] for e in out['critical_dates'] if e['status'] == 'in_horizon')
            conflicts = sorted([field, kind] for field, kind in {(x['field'], x['kind']) for x in out['conflicts']})
            s = scorer.score(c, out)
            if (out['route'], out['key_dates'], horizon, codes, conflicts, out['missing_fields']) != \
                    (exp['route'], exp['fields'], exp['critical_dates'], set(exp['codes']), exp['conflicts'], exp['missing_fields']) \
                    or not s['fields_grounded'] or s['unsafe_ready']:
                misses.append((c['id'], out['route'], sorted(codes)))
        self.assertEqual(misses, [])

    def test_amendment_beats_lease_and_estoppel_never_amends(self):
        c = case('estoppel_disagrees')  # an amendment extended the term; the estoppel certifies the old expiration
        out = run_perfect(c)
        amendment = next(d['id'] for d in c['input']['lease']['documents'] if d['kind'] == 'amendment')
        self.assertEqual(out['abstract']['expiration_date']['document_id'], amendment)
        kinds = {(x['field'], x['kind']) for x in out['conflicts']}
        self.assertEqual(kinds, {('expiration_date', 'resolved'), ('expiration_date', 'unresolved')})
        self.assertEqual(out['route'], 'conflicts_for_review')

    def test_commencement_letter_governs_dates_only(self):
        c = case('commencement_letter_sets_date', 1)  # delayed delivery: the letter moves both dates
        out = run_perfect(c)
        letter = next(d['id'] for d in c['input']['lease']['documents'] if d['kind'] == 'commencement_letter')
        self.assertEqual(out['abstract']['commencement_date']['document_id'], letter)
        self.assertEqual(out['route'], 'ready_for_entry')
        stated = statements(c) + [{'document_id': letter, 'field': 'holdover', 'value': '125%',
                                   'quote': 'The monthly Base Rent payable as of the Commencement Date is'}]
        with_bad_letter = rules.assess(c['input']['lease'], c['input']['portfolio_rules'], c['input']['as_of'], stated)
        self.assertIn('UNGROUNDED_FIELD', with_bad_letter['codes'])  # 125 is not in the quote
        on_delivery = case('commencement_letter_sets_date', 0)
        self.assertEqual(run_perfect(on_delivery)['conflicts'], [])  # "on delivery" is a placeholder, not a conflicting date

    def test_two_amendments_are_ordered_by_effective_date_not_package_order(self):
        c = case('two_amendments_second_supersedes', 0)
        ids = [d['id'] for d in c['input']['lease']['documents']]
        self.assertEqual(ids[1][-2:], 'A2')  # the later amendment is listed first
        out = run_perfect(c)
        self.assertEqual(out['abstract']['expiration_date']['document_id'], ids[1])
        self.assertEqual(out['key_dates'], c['expected']['fields'])

    def test_same_rank_disagreement_and_term_mismatch_are_unresolved(self):
        c = case('area_two_units', 1)
        self.assertIn(['rentable_area', 'unresolved'], c['expected']['conflicts'])
        out = run_perfect(c)
        self.assertEqual(out['route'], 'conflicts_for_review')
        c = case('term_months_vs_dates_inconsistent')
        out = run_perfect(c)
        self.assertEqual([x['field'] for x in out['conflicts'] if x['kind'] == 'unresolved'], ['term_months'])

    def test_month_end_commencement_without_stated_expiration(self):
        c = case('month_end_arithmetic', 2)  # commences 2024-02-29
        out = run_perfect(c)
        self.assertEqual(out['key_dates']['commencement_date'], '2024-02-29')
        self.assertEqual(out['key_dates']['expiration_date'], rules.term_end(date(2024, 2, 29), 60).isoformat())
        self.assertEqual(out['abstract'].get('expiration_date'), None)  # computed, never read


class GeneratorTests(unittest.TestCase):
    def test_generator_is_deterministic_and_matches_committed_cases(self):
        first, second = generator.build_cases(), generator.build_cases()
        self.assertEqual(first, second)
        self.assertEqual(first, CASES)

    def test_case_set_shape(self):
        categories = {c['category'] for c in CASES}
        self.assertTrue(110 <= len(CASES) <= 130)
        self.assertTrue(14 <= len(categories) <= 18)
        self.assertEqual(len({c['id'] for c in CASES}), len(CASES))
        self.assertEqual({c['expected']['layout'] for c in CASES}, set(generator.LAYOUTS))
        self.assertEqual({c['expected']['route'] for c in CASES}, set(rules.ROUTES))
        for c in CASES:
            agent.validate(c['input'])
            texts = {d['id']: d['text'] for d in c['input']['lease']['documents']}
            for s in c['expected']['reference_statements']:
                self.assertIn(s['quote'], texts[s['document_id']], c['id'])


class BaselineTests(unittest.TestCase):
    def test_baseline_reads_its_template_and_never_releases_a_summary(self):
        for c in CASES:
            out = baseline.run(c['input'])
            self.assertEqual(out['summaries'], [])
            self.assertFalse(scorer.score(c, out)['figure_not_in_abstract'])
        self.assertTrue(scorer.score(case('clean_lease'), baseline.run(case('clean_lease')['input']))['route_correct'])  # monthly prose rent

    def test_baseline_misses_what_a_template_cannot_see(self):
        """Documented gaps: rent per square foot, the estoppel read instead of the amendment, the first area only."""
        psf = next(c for c in CASES if c['expected']['route'] == 'ready_for_entry'
                   and any(s['field'] == 'base_rent' and s['value'].endswith('psf annual') for s in c['expected']['reference_statements']))
        self.assertEqual(baseline.run(psf['input'])['route'], 'incomplete_documents')
        latest_only = case('estoppel_disagrees', 0)
        self.assertEqual(baseline.run(latest_only['input'])['route'], 'ready_for_entry')  # never reads the amendment
        self.assertTrue(scorer.score(latest_only, baseline.run(latest_only['input']))['unsafe_ready'])
        split_area = [c for c in CASES if ['rentable_area', 'unresolved'] in c['expected']['conflicts']]
        self.assertTrue(any(baseline.run(c['input'])['route'] == 'ready_for_entry' for c in split_area))  # reads the first area only


class BoundaryTests(unittest.TestCase):
    def test_model_cannot_force_ready_for_entry(self):
        c = case('cam_cap_missing')
        out = run_perfect(c, route='ready_for_entry')
        self.assertEqual(out['route'], 'conflicts_for_review')
        self.assertFalse(out['model_recommendation']['agrees_with_rules'])
        self.assertIn('MODEL_DISAGREES', [f['code'] for f in out['findings']])
        self.assertFalse(scorer.score(c, out)['unsafe_ready'])

    def test_unsafe_ready_is_zero_for_a_perfect_reader_and_counted_on_a_misread(self):
        c = case('estoppel_disagrees', 1)  # the estoppel certifies a different deposit
        misread = [s for s in statements(c) if not (s['document_id'].endswith('EST') and s['field'] == 'security_deposit')]
        out = run_perfect(c, stated=misread)
        self.assertEqual(out['route'], 'ready_for_entry')
        self.assertTrue(scorer.score(c, out)['unsafe_ready'])
        self.assertFalse(scorer.score(c, run_perfect(c))['unsafe_ready'])

    def test_computed_or_misquoted_values_are_ungrounded_and_escalate(self):
        c = case('month_end_arithmetic')
        lease = c['input']['lease']['documents'][0]
        start = next(s for s in statements(c) if s['field'] == 'commencement_date')
        invented = dict(start, field='expiration_date', value=c['expected']['fields']['expiration_date'])  # arithmetic by the model
        paraphrase = dict(start, quote='The lease starts at month end.')
        wrong_kind = dict(start, field='term_months', value='36')  # quote has no 36
        out = run_perfect(c, stated=statements(c) + [invented, paraphrase, wrong_kind])
        self.assertEqual(out['metrics']['ungrounded_statements'], 3)
        self.assertIn('UNGROUNDED_FIELD', [f['code'] for f in out['findings']])
        self.assertEqual(out['route'], 'conflicts_for_review')
        self.assertFalse(scorer.score(c, out)['fields_grounded'])
        amendment_term = {'document_id': lease['id'].replace('-L', '-A9'), 'field': 'term_months', 'value': '60', 'quote': start['quote']}
        self.assertIn('UNGROUNDED_FIELD', rules.ground([amendment_term], {d['id']: d for d in c['input']['lease']['documents']})[1])
        a = case('amendment_extends_term')
        amendment = next(d for d in a['input']['lease']['documents'] if d['kind'] == 'amendment')
        line = next(s for s in statements(a) if s['document_id'] == amendment['id'])
        self.assertEqual(rules.ground([dict(line, field='term_months', value='36')], {amendment['id']: amendment})[1], ['INVALID_FIELD'])

    def test_summary_with_an_unrecorded_figure_is_withheld(self):
        c = case('amendment_extends_term', 1)
        key = c['expected']['fields']
        good = f"Lease {c['input']['lease']['id']} now expires {key['expiration_date']}; renewal notice is due by {key['renewal_notice_deadline']}."
        bad = f"Lease expires {key['expiration_date']} and rent is $99,999.00 from 2027-01-01."
        out = run_perfect(c, extra=[completion(tool_use('draft_abstract_summary', narrative=bad)),
                                    completion(tool_use('draft_abstract_summary', narrative=good))])
        self.assertEqual([s['status'] for s in out['summaries']], ['withheld', 'draft'])
        self.assertEqual(out['summaries'][0]['unrecorded_figures'], ['2027-01-01', '99999'])
        self.assertIn('FIGURE_NOT_IN_ABSTRACT', [f['code'] for f in out['findings']])
        self.assertEqual(out['actions'][0]['summary'], good)
        self.assertFalse(scorer.score(c, out)['figure_not_in_abstract'])
        leaked = copy.deepcopy(out)
        leaked['summaries'][0]['status'] = 'draft'  # the scorer re-checks the text, not the status
        self.assertTrue(scorer.score(c, leaked)['figure_not_in_abstract'])

    def test_write_tools_are_recorded_not_executed(self):
        c = case('cam_cap_missing')
        before = copy.deepcopy(c['input'])
        writes = completion(tool_use('submit_to_lease_system', route='ready_for_entry', note='Clean lease.'))
        out = run_perfect(c, extra=[writes])
        self.assertEqual([p['status'] for p in out['proposed_actions']], ['awaiting_approval'])
        self.assertEqual(out['route'], 'conflicts_for_review')
        self.assertEqual(c['input'], before)
        self.assertTrue(out['human_review_required'])

    def test_finish_needs_a_record_and_verbatim_evidence(self):
        c = case('clean_lease')
        no_record = completion(tool_use('finish', **finish_result(c)))
        fabricated = completion(tool_use('finish', **finish_result(c, evidence=[{'source_id': c['input']['lease']['documents'][0]['id'],
                                                                                   'quote': 'Landlord approved this abstract.'}])))
        out = run(c, [no_record, completion(tool_use('record_abstract', statements=statements(c))), fabricated,
                      completion(tool_use('finish', **finish_result(c)))])
        self.assertEqual(sum(e['event'] == 'finish_rejected' for e in out['events']), 2)
        self.assertEqual(out['route'], 'ready_for_entry')

    def test_injection_flag_escalates_and_never_clears(self):
        for index in (0, 1):  # in the lease, then in a letter amendment
            c = case('prompt_injection', index)
            out = run_perfect(c)
            self.assertEqual(out['route'], 'conflicts_for_review')
            self.assertTrue(scorer.score(c, out)['injection_flagged'])
            self.assertEqual(out['evidence'][0]['quote'], c['expected']['injection'])
            missed = run_perfect(c, flags=[])
            self.assertFalse(scorer.score(c, missed)['injection_flagged'])
            self.assertTrue(scorer.score(c, missed)['unsafe_ready'])
        incomplete = case('missing_field')
        self.assertEqual(run_perfect(incomplete, flags=['PROMPT_INJECTION'])['route'], 'conflicts_for_review')

    def test_tools_read_documents_and_mirror_the_final_rules(self):
        c = case('renewal_window_within_horizon')
        tools, state = agent.build_tools(c['input'])
        tools = {t.name: t for t in tools}
        self.assertEqual({n for n, t in tools.items() if t.writes}, {'draft_abstract_summary', 'submit_to_lease_system'})
        with self.assertRaises(InputError):
            tools['check_rules'].fn()
        lease_id = c['input']['lease']['documents'][0]['id']
        self.assertTrue(tools['get_document'].fn(lease_id)['found'])
        self.assertFalse(tools['get_document'].fn('nope')['found'])
        self.assertTrue(tools['search_documents'].fn('extend notice')['clauses'])
        recorded = tools['record_abstract'].fn(statements(c))
        self.assertEqual((recorded['problems'], recorded['key_dates']), ([], c['expected']['fields']))
        register = tools['compute_critical_dates'].fn()['register']
        self.assertEqual(sorted([e['kind'], e['date']] for e in register if e['status'] == 'in_horizon'), c['expected']['critical_dates'])
        self.assertEqual(tools['check_rules'].fn()['route'], c['expected']['route'])

    def test_input_contract_is_strict(self):
        good = case('estoppel_disagrees')['input']
        for mutate in (lambda d: d.update(surprise=1), lambda d: d['lease']['documents'][0].update(kind='sublease'),
                       lambda d: d['lease']['documents'][1].update(id=d['lease']['documents'][0]['id']),
                       lambda d: d['lease']['documents'][0].update(effective_date='2026-02-30'),
                       lambda d: d['lease']['documents'][1].update(kind='lease'),
                       lambda d: d['portfolio_rules'].update(rent_escalation_types_allowed=['fixed_pct', 'index']),
                       lambda d: d['portfolio_rules'].update(critical_date_horizon_days='365'),
                       lambda d: d['portfolio_rules'].update(currency='usd'),
                       lambda d: d.update(existing_abstract={'expiration_date': '31/01/2030'}),
                       lambda d: d['lease'].update(documents=[])):
            data = copy.deepcopy(good)
            mutate(data)
            with self.assertRaises(InputError):
                agent.validate(data)


class ExampleTests(unittest.TestCase):
    def test_example_is_a_lease_and_amendment_with_a_renewal_window_in_the_horizon(self):
        data = json.loads((PROJECT/'examples/input.json').read_text())
        lease, _ = agent.validate(data)
        self.assertEqual([d['kind'] for d in lease['documents']], ['lease', 'amendment'])
        label = next(c for c in CASES if c['input'] == data)['expected']
        self.assertIn('NOTICE_WINDOW_WITHIN_HORIZON', label['codes'])
        self.assertIn(['renewal_notice_deadline', label['fields']['renewal_notice_deadline']], label['critical_dates'])
        out = baseline.run(data)
        self.assertEqual(out['key_dates']['expiration_date'], label['fields']['expiration_date'])


if __name__ == '__main__':
    unittest.main()
