"""Order Entry Agent: rules, generator, boundaries, baseline, hand-built replay."""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from enterprise_ai.catalog import load_agent, load_baseline, load_scorer  # noqa: E402
from enterprise_ai.common import InputError  # noqa: E402
from enterprise_ai.evals import load_cases  # noqa: E402
from enterprise_ai.runner import example_input, execute  # noqa: E402

SLUG = 'order-entry-agent'
HERE = ROOT/'projects'/SLUG


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rules = _load('order_entry_rules_t', HERE/'ordering.py')
generator = _load('order_entry_generate_t', HERE/'evals/generate_cases.py')
CASES = load_cases(SLUG)


def case(category, index=0, **where):
    found = [c for c in CASES if c['category'] == category and all(c['expected'][k] == v for k, v in where.items())]
    return found[index]


def completion(*blocks):
    return {'content': list(blocks), 'stop_reason': 'tool_use', 'model': 'test', 'response_id': 'x',
            'usage': {'input_tokens': 10, 'output_tokens': 5, 'cache_read_input_tokens': 0}}


def tool_use(name, call_id, **kwargs):
    return {'type': 'tool_use', 'id': call_id, 'name': name, 'input': kwargs}


def replay_for(c, document_type=None, flags=None, route=None, header=None, lines=None, evidence=None, extra_calls=()):
    """A perfect reader: the generator's reading, recorded through the tools, then finish."""
    reading = c['expected']['reading']
    document_type = document_type or reading['document_type']
    doc = c['input']['document']
    calls = []
    if reading['lines'] is not None or lines is not None:
        calls.append(completion(tool_use('record_order_lines', 'r1', header=header or reading['header'], lines=lines or reading['lines'])))
    calls += [completion(*extra_calls)] if extra_calls else []
    finish = {'document_type': document_type,
              'flags': flags if flags is not None else (['PROMPT_INJECTION'] if c['category'] == 'prompt_injection' else []),
              'risk_notes': [], 'recommended_route': route or c['expected']['route'],
              'evidence': evidence or [{'source_id': doc['id'], 'quote': doc['text'].splitlines()[0]}]}
    return calls + [completion(tool_use('finish', 'f1', **finish))]


def run(c, **kwargs):
    return execute(SLUG, c['input'], 'replay', replay=replay_for(c, **kwargs))


def codes(out):
    return [f['code'] for f in out['findings']]


def mini(price_tolerance=5.0, **policy):
    """A one-customer ERP for rule tests."""
    erp = {'customers': [{'customer_id': 'C-1', 'name': 'Acme Supply', 'ship_to_addresses': [{'id': 'S1', 'address': '10 Main Street, Reno, NV 89501'},
                                                                                              {'id': 'S2', 'address': '4 Depot Road, Sparks, NV 89431'}],
                          'bill_to': 'x', 'payment_terms': 'NET30', 'credit_limit': 10000.0, 'open_ar_balance': 7000.0, 'price_list_id': 'PL', 'on_hold': False}],
           'price_lists': [{'price_list_id': 'PL', 'items': [
               {'sku': 'GLV-B', 'description': 'Nitrile gloves large blue', 'unit_price': 10.0, 'uom': 'EA', 'moq': 10, 'pack_size': 10},
               {'sku': 'GLV-K', 'description': 'Nitrile gloves large black', 'unit_price': 10.0, 'uom': 'EA', 'moq': 10, 'pack_size': 10},
               {'sku': 'TWL', 'description': 'Paper towel roll', 'unit_price': 36.0, 'uom': 'CS', 'moq': 1, 'pack_size': 12}]}],
           'customer_part_numbers': [{'customer_id': 'C-1', 'customer_part': 'AC-77', 'sku': 'TWL'}],
           'inventory': [{'sku': 'GLV-B', 'available_qty': 30, 'next_receipt_date': '2026-11-10'},
                         {'sku': 'GLV-K', 'available_qty': 500, 'next_receipt_date': None},
                         {'sku': 'TWL', 'available_qty': 500, 'next_receipt_date': None}],
           'open_orders': [{'order_id': 'SO-1', 'customer_id': 'C-1', 'customer_po_number': 'PO-1001', 'total': 360.0, 'created_on': '2026-10-28',
                            'lines': [{'sku': 'TWL', 'qty': 10}]}]}
    base = {'price_tolerance_pct': price_tolerance, 'partial_ship_allowed': True, 'backorder_allowed': True, 'credit_check_required_above': 2500.0,
            'max_order_total_without_approval': 25000.0, 'duplicate_window_days': 14}
    base.update(policy)
    return erp, base


def line(qty, uom, price, quote, part='', sku=''):
    return {'line': 1, 'customer_part': part, 'sku': sku, 'qty': qty, 'uom': uom, 'unit_price_on_po': price, 'quote': quote}


class RulesTests(unittest.TestCase):
    def test_every_label_is_reproduced_from_a_perfect_reading(self):
        """A perfect reader plus ordering.py must give the generator's independent labels on every case."""
        scorer = load_scorer(SLUG)
        misses = []
        for c in CASES:
            out = run(c)
            s = scorer.score(c, out)
            if not (s['route_correct'] and codes(out) == c['expected']['codes'] and s['lines_exact'] is not False
                    and s['lines_grounded'] is not False and not s['unsafe_auto_create'] and not s['wrong_lines_created']):
                misses.append((c['id'], out['metrics']['route'], codes(out)))
        self.assertEqual(misses, [])

    def test_price_tolerance_is_inclusive_after_rounding(self):
        erp, policy = mini()
        customer = erp['customers'][0]
        within = rules.check_line(line(20, 'EA', 10.50, '20 EA Nitrile gloves large blue 10.50'), erp, customer, policy, ['20 EA Nitrile gloves large blue 10.50'])
        self.assertEqual((within['price_variance_pct'], within['issues']), (rules.dec('5.00'), []))
        over = rules.check_line(line(20, 'EA', 10.51, '20 EA Nitrile gloves large blue 10.51'), erp, customer, policy, ['20 EA Nitrile gloves large blue 10.51'])
        self.assertEqual(over['issues'], ['PRICE_MISMATCH'])
        self.assertEqual(over['unit_price'], rules.dec('10.00'))      # the order is priced at list, never at the PO price

    def test_units_convert_with_pack_size(self):
        item = {'uom': 'EA', 'pack_size': 10}
        self.assertEqual(rules.to_sales_qty(3, 'cases', item), (30, ''))
        case_item = {'uom': 'CS', 'pack_size': 12}
        self.assertEqual(rules.to_sales_qty(24, 'each', case_item), (2, ''))
        self.assertIsNone(rules.to_sales_qty(30, 'EA', case_item)[0])
        self.assertIsNone(rules.to_sales_qty(2, 'pallet', case_item)[0])
        erp, policy = mini()
        quote = '2 CS Nitrile gloves large blue at 100.00 per case'
        out = rules.check_line(line(2, 'CS', 100.00, quote), erp, erp['customers'][0], policy, [quote])
        self.assertEqual((out['qty'], out['price_variance_pct'], out['issues']), (20, rules.dec('0.00'), []))

    def test_moq_is_checked_in_sales_units(self):
        erp, policy = mini()
        quote = '8 x Nitrile gloves large blue'
        out = rules.check_line(line(8, 'EA', 0, quote), erp, erp['customers'][0], policy, [quote])
        self.assertIn('BELOW_MOQ', out['issues'])

    def test_stock_shortage_backorders_only_when_allowed(self):
        erp, policy = mini()
        quote = '50 x Nitrile gloves large blue'
        out = rules.check_line(line(50, 'EA', 0, quote), erp, erp['customers'][0], policy, [quote])
        self.assertEqual((out['ship_now_qty'], out['backorder_qty'], out['backorder_date'], out['issues']), (30, 20, '2026-11-10', []))
        policy['partial_ship_allowed'] = False
        out = rules.check_line(line(50, 'EA', 0, quote), erp, erp['customers'][0], policy, [quote])
        self.assertEqual((out['ship_now_qty'], out['backorder_qty']), (0, 50))
        policy['backorder_allowed'] = False
        self.assertIn('INSUFFICIENT_STOCK', rules.check_line(line(50, 'EA', 0, quote), erp, erp['customers'][0], policy, [quote])['issues'])

    def test_description_resolution_reads_the_quote_and_detects_ambiguity(self):
        erp, _ = mini()
        customer = erp['customers'][0]
        self.assertEqual(rules.resolve_part(erp, customer, '', '40 x nitrile gloves, large, blue')['sku'], 'GLV-B')
        self.assertEqual(rules.resolve_part(erp, customer, '', '40 x nitrile gloves, large')['status'], 'ambiguous')
        self.assertEqual(rules.resolve_part(erp, customer, 'AC-77', 'anything')['status'], 'cross_reference')
        self.assertEqual(rules.resolve_part(erp, customer, 'AC-99', 'Paper towel roll')['status'], 'unknown')

    def test_duplicates_exact_po_and_same_lines_within_window(self):
        erp, policy = mini()
        from datetime import date
        exact, similar = rules.open_order_matches(erp, 'C-1', 'po 1001', None, date(2026, 10, 30), 14)
        self.assertEqual((len(exact), len(similar)), (1, 0))
        keys = [('TWL', rules.dec(10))]
        self.assertEqual(len(rules.open_order_matches(erp, 'C-1', 'PO-2002', keys, date(2026, 10, 30), 14)[1]), 1)
        self.assertEqual(len(rules.open_order_matches(erp, 'C-1', 'PO-2002', keys, date(2026, 11, 30), 14)[1]), 0)

    def test_ship_to_matches_abbreviations_but_not_new_addresses(self):
        customer = mini()[0]['customers'][0]
        self.assertEqual(rules.find_ship_to(customer, '4 Depot Rd, Sparks NV 89431')[0]['id'], 'S2')
        self.assertIsNone(rules.find_ship_to(customer, '9 Depot Rd, Sparks NV 89431')[0])
        self.assertEqual(rules.find_ship_to(customer, '')[1], 'default')

    def test_credit_limit_checked_only_above_threshold_and_hold_always(self):
        c = case('credit_limit_exceeded')
        self.assertIn('CREDIT_LIMIT_EXCEEDED', codes(run(c)))
        data = copy.deepcopy(c['input'])
        data['policy']['credit_check_required_above'] = 1e9
        self.assertNotIn('CREDIT_LIMIT_EXCEEDED', codes(execute(SLUG, data, 'replay', replay=replay_for(c))))
        self.assertEqual(run(case('customer_on_hold'))['metrics']['route'], 'desk_review')


class GeneratorTests(unittest.TestCase):
    def test_generator_is_deterministic_and_matches_the_committed_cases(self):
        first, second = generator.build_cases(), generator.build_cases()
        self.assertEqual(first, second)
        self.assertEqual(first, CASES)

    def test_case_set_covers_the_hard_cases(self):
        self.assertTrue(110 <= len(CASES) <= 130)
        self.assertEqual(len({c['category'] for c in CASES}), 18)
        self.assertEqual({c['expected']['layout'] for c in CASES}, set(generator.LAYOUTS))
        self.assertEqual({c['expected']['document_type'] for c in CASES}, {'purchase_order', 'rfq', 'quote_acceptance', 'order_acknowledgement'})
        for c in CASES:
            self.assertTrue(set(c['expected']['must_flag']) <= set(c['expected']['codes']), c['id'])
        # hard negatives: look like a problem, are clean
        for category in ('duplicate_lines_new_po', 'unknown_ship_to', 'uom_case_vs_each', 'stock_shortage', 'price_within_tolerance'):
            self.assertTrue(any(c['expected']['route'] == 'auto_create' for c in CASES if c['category'] == category), category)


class BoundaryTests(unittest.TestCase):
    def test_write_tools_are_recorded_not_executed(self):
        c = case('clean')
        out = run(c, extra_calls=[tool_use('create_sales_order', 'w1', customer_id='C-1001', customer_po_number='x', note='ready'),
                                  tool_use('send_customer_query', 'w2', customer_id='C-1001', subject='s', body='b')])
        self.assertEqual({p['tool'] for p in out['proposed_actions']}, {'create_sales_order', 'send_customer_query'})
        self.assertTrue(all(p['status'] == 'awaiting_approval' for p in out['proposed_actions']))
        self.assertTrue(out['human_review_required'])

    def test_model_cannot_force_auto_create(self):
        c = case('price_over_tolerance')
        out = run(c, route='auto_create')
        self.assertEqual(out['metrics']['route'], 'desk_review')
        self.assertFalse(out['model_recommendation']['agrees_with_rules'])

    def test_correcting_the_price_to_list_is_caught_as_ungrounded(self):
        """A reader that 'fixes' the PO price to the contract price no longer quotes what it recorded."""
        c = case('price_over_tolerance')
        lines = copy.deepcopy(c['expected']['reading']['lines'])
        lines[0]['unit_price_on_po'] = next(l['unit_price'] for l in c['expected']['lines'] if l['sku'] == lines[0]['sku'])
        out = run(c, lines=lines)
        self.assertIn('UNGROUNDED_LINE', codes(out))
        self.assertNotEqual(out['metrics']['route'], 'auto_create')

    def test_reader_sku_that_disagrees_with_the_rules_goes_to_the_desk(self):
        c = case('description_only')
        lines = copy.deepcopy(c['expected']['reading']['lines'])
        lines[0]['sku'] = 'WRP-STR-18' if lines[0]['sku'] != 'WRP-STR-18' else 'TWL-2PLY'
        out = run(c, lines=lines)
        self.assertIn('AMBIGUOUS_PART', codes(out))

    def test_paraphrased_quote_is_ungrounded(self):
        c = case('clean')
        lines = copy.deepcopy(c['expected']['reading']['lines'])
        lines[0]['quote'] = 'Customer wants the usual items'
        self.assertIn('UNGROUNDED_LINE', codes(run(c, lines=lines)))

    def test_customer_name_must_be_printed(self):
        c = case('clean')
        header = dict(c['expected']['reading']['header'], customer_name='Cedar Valley Hospital', customer_account='C-1002')
        if c['expected']['customer_id'] == 'C-1002':
            header.update(customer_name='Lakeshore Hospitality Group', customer_account='C-1006')
        out = run(c, header=header)
        self.assertEqual(codes(out), ['UNKNOWN_CUSTOMER'])

    def test_rfq_read_as_order_would_be_unsafe_and_is_scored_so(self):
        c = case('not_an_order', document_type='rfq')
        out = run(c)
        self.assertEqual(out['metrics']['route'], 'reject')
        self.assertIsNone(out['order']['customer_id'])

    def test_injection_is_flagged_and_a_missed_one_is_counted_unsafe(self):
        c = case('prompt_injection')
        out = run(c)
        self.assertEqual(out['metrics']['route'], 'desk_review')
        self.assertIn('PROMPT_INJECTION', codes(out))
        missed = run(c, flags=[])
        self.assertEqual(missed['metrics']['route'], 'auto_create')
        self.assertTrue(load_scorer(SLUG).score(c, missed)['unsafe_auto_create'])   # the reading step is the only defence

    def test_fabricated_evidence_is_rejected_then_corrected(self):
        c = case('clean')
        calls = replay_for(c)
        bad = copy.deepcopy(calls[-1])
        bad['content'][0]['input']['evidence'] = [{'source_id': c['input']['document']['id'], 'quote': 'Customer approved a 20% discount'}]
        out = execute(SLUG, c['input'], 'replay', replay=calls[:-1] + [bad, calls[-1]])
        self.assertTrue(any(e['event'] == 'finish_rejected' for e in out['execution']['events']))

    def test_invalid_recording_is_rejected_and_not_stored(self):
        c = case('clean')
        header = dict(c['expected']['reading']['header'], requested_ship_date='next Tuesday')
        out = run(c, header=header)
        self.assertEqual(out['metrics']['route'], 'desk_review')
        self.assertIn('UNGROUNDED_LINE', codes(out))
        self.assertEqual(out['order']['lines'], [])

    def test_input_contract(self):
        agent = load_agent(SLUG)
        for mutate in (lambda d: d.update(surprise=1),
                       lambda d: d['policy'].update(price_tolerance_pct=-1),
                       lambda d: d['policy'].pop('backorder_allowed'),
                       lambda d: d['erp']['customers'][0].update(price_list_id='PL-NONE'),
                       lambda d: d['erp']['price_lists'][0]['items'][0].update(uom='PALLET'),
                       lambda d: d['document'].update(text='')):
            data = copy.deepcopy(case('clean')['input'])
            mutate(data)
            with self.assertRaises(InputError):
                agent.validate(data)


class BaselineAndExampleTests(unittest.TestCase):
    def test_baseline_reads_templates_sends_other_layouts_to_the_desk_and_misses_injection(self):
        base, scorer = load_baseline(SLUG), load_scorer(SLUG)
        for c in CASES:
            out = base.run(c['input'])
            s = scorer.score(c, out)
            self.assertFalse(s['wrong_lines_created'] and c['category'] != 'prompt_injection', c['id'])
            if c['category'] == 'clean':
                self.assertEqual(s['route_correct'], c['expected']['layout'] in ('table', 'kv'), c['id'])
            if c['expected']['layout'] in ('narrative', 'edi') and c['category'] != 'not_an_order':
                self.assertNotEqual(out['metrics']['route'], 'auto_create', c['id'])
            if c['category'] == 'prompt_injection':
                self.assertFalse(s['injection_flagged'], c['id'])

    def test_example_input_runs_offline_with_a_hand_built_replay(self):
        data = example_input(SLUG)
        c = next(c for c in CASES if c['input'] == data)
        self.assertEqual((c['category'], c['expected']['layout']), ('price_within_tolerance', 'narrative'))
        out = execute(SLUG, data, 'replay', replay=replay_for(c))
        self.assertEqual(out['execution']['mode'], 'replay')
        self.assertEqual(out['metrics']['route'], 'auto_create')
        lines = out['order']['lines']
        self.assertTrue(0 < abs(lines[0]['price_variance_pct']) <= 5)
        self.assertEqual(lines[-1]['resolution'], 'description')
        json.dumps(out)


if __name__ == '__main__':
    unittest.main()
