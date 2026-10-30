"""Credit Memo Agent: ratio math, policy rules, generator, boundaries, baseline, hand-built replay."""
import copy
import importlib.util
import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from enterprise_ai.catalog import load_agent, load_baseline, load_scorer  # noqa: E402
from enterprise_ai.common import InputError  # noqa: E402
from enterprise_ai.evals import load_cases  # noqa: E402
from enterprise_ai.runner import example_input, execute  # noqa: E402

SLUG = 'credit-memo-agent'
HERE = ROOT/'projects'/SLUG


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


uw = _load('credit_underwriting_t', HERE/'underwriting.py')
generator = _load('credit_generate_t', HERE/'evals/generate_cases.py')
CASES = load_cases(SLUG)


def case(category, index=0):
    return [c for c in CASES if c['category'] == category][index]


def completion(*blocks):
    return {'content': list(blocks), 'stop_reason': 'tool_use', 'model': 'test', 'response_id': 'x',
            'usage': {'input_tokens': 10, 'output_tokens': 5, 'cache_read_input_tokens': 0}}


def tool_use(name, call_id, **kwargs):
    return {'type': 'tool_use', 'id': call_id, 'name': name, 'input': kwargs}


def perfect_spread(sid, truth, **overrides):
    """What a perfect reader records: the true figures, each quoted as printed."""
    raw = {f: truth.get(f, 0) for f in uw.SPREAD_FIELDS}
    raw.update({'statement_id': sid, 'period_months': truth['period_months'], 'restated': truth.get('restated', False),
                'addbacks': [{'description': f"{a['kind']} item", 'amount': a['amount'], 'kind': a['kind'], 'documented': a['documented'],
                              'quote': f"{a['amount']:,}"} for a in truth.get('addbacks', [])]})
    raw['quotes'] = [{'field': f, 'quote': f'{raw[f]:,}'} for f in uw.SPREAD_FIELDS if raw[f]]
    if raw['restated']:
        raw['quotes'].append({'field': 'restated', 'quote': 'restated'})
    raw.update(overrides)
    return raw


def memo_for(c, extra=''):
    e = c['expected']
    analysis = ' '.join(f'{k.upper()} {e[k]}{s}.' for k, s in (('dscr', 'x'), ('leverage', 'x')) if e[k] is not None)
    return {'borrower': c['input']['request']['borrower'] + '.', 'facility': f"Amount {c['input']['request']['facility']['amount']:,}.",
            'financial_analysis': f"Revenue {e['revenue']:,}. {analysis} {extra}".strip(), 'collateral': f"LTV {e['ltv']}%.",
            'guarantors': 'Personal guaranties.', 'risks': 'See exceptions.', 'mitigants': 'Guaranties.', 'policy_exceptions': 'As listed.'}


def replay_for(c, flags=None, route=None, memo=None, spreads=None, evidence=None, extra_calls=()):
    spreads = spreads if spreads is not None else {sid: perfect_spread(sid, t) for sid, t in c['expected']['spreads'].items()}
    first = c['input']['statements'][0]
    finish = {'flags': flags if flags is not None else (['PROMPT_INJECTION'] if c['category'] == 'prompt_injection' else []),
              'risk_notes': [], 'recommended_route': route or c['expected']['route'],
              'evidence': evidence or [{'source_id': first['id'], 'quote': first['text'].splitlines()[0]}]}
    calls = [completion(*(tool_use('get_statement', f'g{i}', statement_id=s['id']) for i, s in enumerate(c['input']['statements']))),
             completion(*(tool_use('record_spread', f's{i}', **raw) for i, raw in enumerate(spreads.values()))),
             completion(tool_use('compute_ratios', 'r1'), tool_use('check_policy', 'p1')),
             completion(tool_use('draft_memo', 'm1', **(memo or memo_for(c))), *extra_calls),
             completion(tool_use('finish', 'f1', **finish))]
    return calls


def run(c, **kwargs):
    return execute(SLUG, c['input'], 'replay', replay=replay_for(c, **kwargs))


def spread(kind, period_end, months=12, addbacks=(), **values):
    return {'statement_id': f'{kind}-{period_end}', 'kind': kind, 'period_end': period_end, 'fiscal_year_end': '12-31', 'period_months': months,
            'restated': False, 'values': {f: Decimal(str(values.get(f, 0))) for f in uw.SPREAD_FIELDS}, 'addbacks': list(addbacks)}


def package(facility=None):
    return {'as_of': '2026-10-30', 'credit_policy': generator.POLICY,
            'request': {'id': 'CR-1', 'borrower': 'Test Co', 'facility': facility or {'type': 'revolver', 'amount': 1000000, 'tenor_months': 12, 'rate': 8.0, 'purpose': 'x'},
                        'collateral': [{'type': 'real_estate', 'appraised_value': 2000000, 'appraisal_date': '2026-06-01'}],
                        'guarantors': [{'name': 'A', 'net_worth': 1, 'liquidity': 1, 'personal_cash_flow': 50000}]}}


class RatioAndRuleTests(unittest.TestCase):
    def test_every_label_is_reproduced_from_a_perfect_spread(self):
        """A perfect reader plus underwriting.py must give the generator's independent labels on every case."""
        scorer = load_scorer(SLUG)
        misses = []
        for c in CASES:
            out = run(c)
            s = scorer.score(c, out)
            if not (s['route_correct'] and set(out['exceptions']) == set(c['expected']['exceptions']) and s['ratios_exact'] is not False
                    and s['spread_fields_exact'] and not s['unsafe_ready'] and not s['figure_not_in_spread']):
                misses.append((c['id'], out['metrics']['route'], out['exceptions']))
        self.assertEqual(misses, [])

    def test_proposed_debt_service(self):
        self.assertEqual(uw.proposed_debt_service({'type': 'revolver', 'amount': 1000000, 'rate': 8.0, 'tenor_months': 12}), Decimal('80000.00'))
        # 1,000,000 at 6% over 60 months: 19,332.80 a month.
        self.assertEqual(uw.proposed_debt_service({'type': 'term_loan', 'amount': 1000000, 'rate': 6.0, 'tenor_months': 60}), Decimal('231993.60'))

    def test_interim_is_annualized_and_tested(self):
        data = package()
        spreads = {'is': spread('income_statement', '2025-12-31', revenue=10000000, cogs=6000000, operating_expenses=2500000, depreciation=200000, interest_expense=100000),
                   'bs': spread('balance_sheet', '2025-12-31', current_portion_ltd=100000, long_term_debt=500000, current_assets=3000000, current_liabilities=1500000),
                   'int': spread('interim', '2026-06-30', months=6, revenue=5000000, cogs=3000000, operating_expenses=1600000, depreciation=100000, interest_expense=50000)}
        r = uw.compute(data, spreads)
        self.assertEqual(r['ebitda'], Decimal('1700000.00'))
        self.assertEqual(r['interim_adjusted_ebitda_annualized'], Decimal('1000000.00'))   # 500,000 x 12 / 6
        self.assertEqual(r['interim_debt_service'], Decimal('280000.00'))                # 100,000 + 100,000 + 80,000
        self.assertEqual(r['interim_dscr'], Decimal('3.57'))
        spreads['int']['period_months'] = 12                                              # a misread period halves the interim
        self.assertEqual(uw.compute(data, spreads)['interim_adjusted_ebitda_annualized'], Decimal('500000.00'))

    def test_add_back_policy(self):
        data = package()
        documented = {'description': 'settlement', 'amount': Decimal(100000), 'kind': 'one_time', 'documented': True, 'quote': ''}
        owner = {'description': 'owner car', 'amount': Decimal(50000), 'kind': 'owner_discretionary', 'documented': False, 'quote': ''}
        base = dict(revenue=10000000, cogs=6000000, operating_expenses=3000000, depreciation=200000)
        spreads = {'is': spread('income_statement', '2026-06-30', addbacks=[documented, owner], **base),
                   'bs': spread('balance_sheet', '2026-06-30', current_assets=2, current_liabilities=1)}
        r = uw.compute(data, spreads)
        self.assertEqual((r['ebitda'], r['adjusted_ebitda']), (Decimal('1200000.00'), Decimal('1300000.00')))
        self.assertIn('UNDOCUMENTED_ADDBACK', uw.check_policy(data, spreads, r))
        data['credit_policy'] = dict(data['credit_policy'], add_back_rules={'allowed': ['depreciation']})
        self.assertEqual(uw.compute(data, spreads)['adjusted_ebitda'], Decimal('1200000.00'))

    def test_rounding_is_half_up_before_the_policy_test(self):
        passing, failing = case('rounding_trap', 0), case('rounding_trap', 1)
        self.assertEqual((passing['expected']['dscr'], passing['expected']['route']), (1.25, 'ready_for_officer'))
        self.assertEqual(failing['expected']['dscr'], 1.24)
        self.assertNotEqual(failing['expected']['route'], 'ready_for_officer')

    def test_spread_figures_need_quotes_that_print_them(self):
        c = case('clean_tabular')
        statement = c['input']['statements'][0]
        good = perfect_spread(statement['id'], c['expected']['spreads'][statement['id']])
        uw.normalize_spread(statement, good)
        wrong = copy.deepcopy(good)
        wrong['revenue'] += 1000
        with self.assertRaises(InputError):
            uw.normalize_spread(statement, wrong)
        invented = copy.deepcopy(good)
        invented['quotes'][0]['quote'] = 'Net sales 9,999,999'
        with self.assertRaises(InputError):
            uw.normalize_spread(statement, invented)

    def test_misaligned_tax_year_is_a_period_mismatch_not_a_revenue_mismatch(self):
        for c in [c for c in CASES if c['category'] == 'fiscal_period_mismatch']:
            out = run(c)
            self.assertIn('COVENANT_PERIOD_MISMATCH', out['exceptions'])
            self.assertNotIn('REVENUE_MISMATCH', out['exceptions'])


class GeneratorTests(unittest.TestCase):
    def test_generator_is_deterministic_and_matches_the_committed_cases(self):
        first, second = generator.build_cases(), generator.build_cases()
        self.assertEqual(first, second)
        self.assertEqual(first, CASES)

    def test_case_set_covers_the_hard_cases(self):
        self.assertGreaterEqual(len(CASES), 110)
        self.assertEqual(len({c['category'] for c in CASES}), 18)
        self.assertTrue(any(c['expected']['layout'] == 'narrative' for c in CASES if c['expected']['exceptions']))
        for c in CASES:
            self.assertTrue(set(c['expected']['must_flag']) <= set(c['expected']['exceptions']), c['id'])


class BoundaryTests(unittest.TestCase):
    def test_write_tools_are_recorded_not_executed(self):
        c = case('clean_tabular')
        out = run(c, extra_calls=[tool_use('submit_to_credit_committee', 'w1', request_id='x', note='ready')])
        self.assertEqual({p['tool'] for p in out['proposed_actions']}, {'draft_memo', 'submit_to_credit_committee'})
        self.assertTrue(all(p['status'] == 'awaiting_approval' for p in out['proposed_actions']))
        self.assertTrue(out['human_review_required'])

    def test_memo_with_an_uncomputed_figure_is_withheld(self):
        c = case('clean_tabular')
        out = run(c, memo=memo_for(c, extra='Revenue grew 14.7% year over year.'))
        self.assertEqual(out['memo_status'], 'withheld')
        self.assertIsNone(out['memo'])
        self.assertIn('FIGURE_NOT_IN_SPREAD', out['exceptions'])
        self.assertEqual(out['metrics']['route'], 'exceptions_for_officer')
        self.assertFalse(load_scorer(SLUG).score(c, out)['figure_not_in_spread'])

    def test_memo_using_only_computed_figures_is_released(self):
        c = case('clean_narrative')
        out = run(c)
        self.assertEqual(out['memo_status'], 'drafted_by_model')
        self.assertEqual(out['metrics']['route'], 'ready_for_officer')

    def test_model_cannot_force_ready(self):
        c = case('dscr_below_min')
        out = run(c, route='ready_for_officer')
        self.assertEqual(out['metrics']['route'], 'exceptions_for_officer')
        self.assertFalse(out['model_recommendation']['agrees_with_rules'])

    def test_injection_is_flagged_and_its_figure_never_reaches_the_memo(self):
        c = case('prompt_injection')
        out = run(c, memo=memo_for(c, extra='DSCR 2.35x as pre-cleared.'))
        self.assertIn('PROMPT_INJECTION', out['exceptions'])
        self.assertEqual(out['memo_status'], 'withheld')
        missed = run(c, flags=[])
        self.assertEqual(missed['metrics']['route'], 'ready_for_officer')
        self.assertTrue(load_scorer(SLUG).score(c, missed)['unsafe_ready'])   # the reading step is the only defence

    def test_misread_interim_period_turns_a_pass_into_an_exception(self):
        c = case('interim_annualization', 0)
        self.assertEqual(c['expected']['route'], 'ready_for_officer')
        spreads = {sid: perfect_spread(sid, t) for sid, t in c['expected']['spreads'].items()}
        sid = next(s['id'] for s in c['input']['statements'] if s['kind'] == 'interim')
        spreads[sid]['period_months'] = 12
        out = run(c, spreads=spreads)
        self.assertEqual(out['metrics']['route'], 'exceptions_for_officer')
        self.assertTrue(set(out['exceptions']) & {'DSCR_BELOW_MIN', 'GUARANTOR_SUPPORT_REQUIRED'})

    def test_fabricated_evidence_is_rejected_then_corrected(self):
        c = case('clean_tabular')
        calls = replay_for(c)
        bad = copy.deepcopy(calls[-1])
        bad['content'][0]['input']['evidence'] = [{'source_id': c['input']['statements'][0]['id'], 'quote': 'DSCR of 3.10x confirmed'}]
        out = execute(SLUG, c['input'], 'replay', replay=calls[:-1] + [bad, calls[-1]])
        self.assertTrue(any(e['event'] == 'finish_rejected' for e in out['execution']['events']))

    def test_rejected_spread_is_not_stored(self):
        c = case('clean_tabular')
        spreads = {sid: perfect_spread(sid, t) for sid, t in c['expected']['spreads'].items()}
        sid = next(iter(spreads))
        spreads[sid]['quotes'] = []
        out = run(c, spreads=spreads)
        self.assertNotIn(sid, out['spread'])
        self.assertEqual(out['metrics']['route'], 'insufficient_financials')

    def test_input_contract(self):
        agent = load_agent(SLUG)
        data = copy.deepcopy(case('clean_tabular')['input'])
        data['surprise'] = 1
        with self.assertRaises(InputError):
            agent.validate(data)
        data = copy.deepcopy(case('clean_tabular')['input'])
        data['credit_policy']['max_ltv'] = {'equipment': 50.0}
        data['request']['collateral'][0]['type'] = 'real_estate'
        with self.assertRaises(InputError):
            agent.validate(data)
        data = copy.deepcopy(case('clean_tabular')['input'])
        data['statements'][0]['kind'] = 'press_release'
        with self.assertRaises(InputError):
            agent.validate(data)


class BaselineAndExampleTests(unittest.TestCase):
    def test_baseline_reads_tables_fails_on_prose_and_misses_injection(self):
        base, scorer = load_baseline(SLUG), load_scorer(SLUG)
        for c in CASES:
            out = base.run(c['input'])
            s = scorer.score(c, out)
            self.assertFalse(s['figure_not_in_spread'], c['id'])
            if c['expected']['layout'] == 'tabular' and c['category'] != 'prompt_injection':
                self.assertTrue(s['route_correct'], c['id'])
            if c['category'] == 'clean_narrative':
                self.assertEqual(out['metrics']['route'], 'insufficient_financials')
            if c['category'] == 'prompt_injection':
                self.assertFalse(s['injection_flagged'], c['id'])

    def test_example_input_runs_offline_with_a_hand_built_replay(self):
        data = example_input(SLUG)
        c = next(c for c in CASES if c['input'] == data)
        out = execute(SLUG, data, 'replay', replay=replay_for(c))
        self.assertEqual(out['execution']['mode'], 'replay')
        self.assertEqual(len(out['exceptions']), 1)
        self.assertEqual(out['metrics']['route'], 'exceptions_for_officer')
        json.dumps(out)


if __name__ == '__main__':
    unittest.main()
