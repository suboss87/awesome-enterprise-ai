"""AP Exception Agent: rules, baseline, adversarial boundaries, example replay."""
import copy
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from enterprise_ai.agent import Trace  # noqa: E402
from enterprise_ai.catalog import load_agent, load_baseline, load_scorer  # noqa: E402
from enterprise_ai.common import InputError  # noqa: E402
from enterprise_ai.evals import load_cases  # noqa: E402
from enterprise_ai.llm import ReplayProvider  # noqa: E402
from enterprise_ai.runner import example_input, example_replay, execute  # noqa: E402

SLUG = 'ap-exception-agent'
_spec = importlib.util.spec_from_file_location('ap_matching_t', ROOT/'projects'/SLUG/'matching.py')
matching = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(matching)


def case(category, index=0):
    return [c for c in load_cases(SLUG) if c['category'] == category][index]


def finish_call(result):
    return {'content': [{'type': 'tool_use', 'id': 'f1', 'name': 'finish', 'input': result}], 'stop_reason': 'tool_use',
            'model': 'test', 'response_id': 'x', 'usage': {'input_tokens': 10, 'output_tokens': 5, 'cache_read_input_tokens': 0}}


def perfect_result(c, flags=(), route=None, doc_type='invoice', notes=()):
    """Build a finish payload from the case's own expectations (a 'perfect reader')."""
    exp = c['expected']
    base = load_baseline(SLUG).extract(c['input']['invoice']['text'])[1]
    base.update({'invoice_number': exp['invoice_number'], 'po_numbers': exp['po_numbers'], 'gross_total': exp['gross_total']})
    return {'document_type': doc_type, 'extracted': base, 'flags': list(flags), 'risk_notes': list(notes),
            'recommended_route': route or exp['route'], 'evidence': [{'source_id': c['input']['invoice']['id'], 'quote': exp['invoice_number']}]}


class RulesTests(unittest.TestCase):
    def test_every_expected_route_is_reproduced_by_rules_from_a_perfect_extraction(self):
        """If the model reads perfectly, matching.py alone must produce the labeled route."""
        agent = load_agent(SLUG)
        misses = []
        for c in load_cases(SLUG):
            if c['category'] in ('prompt_injection',):
                continue  # only the model can see this
            exp = c['expected']
            result = perfect_result(c, flags=[f for f in exp['flags'] if f in matching.MODEL_ONLY_FLAGS],
                                    doc_type=exp['document_type'])
            if c['expected']['layout'] in ('narrative', 'european'):
                # the baseline extractor cannot read lines here; rebuild lines from the PO for a perfect read
                result['extracted'] = _lines_from_case(c, result['extracted'])
            out = execute(SLUG, c['input'], 'replay', replay=[finish_call(result)])
            if out['metrics']['route'] != exp['route']:
                misses.append((c['id'], out['metrics']['route'], [f['code'] for f in out['findings']]))
        self.assertEqual(misses, [])

    def test_exact_duplicate_rejects_and_transposed_number_reviews(self):
        erp = {'vendors': [{'vendor_id': 'V1', 'name': 'Acme', 'tax_id': 'T', 'bank_iban': 'GB00'}], 'purchase_orders': [], 'goods_receipts': [],
               'ap_ledger': [{'invoice_number': 'INV-1234', 'vendor_id': 'V1', 'gross_total': 100.0, 'invoice_date': '2026-10-01', 'status': 'paid'}]}
        exact, suspected = matching.ledger_matches(erp, 'V1', 'INV-1234', 100.0, '2026-10-05')
        self.assertEqual(len(exact), 1)
        exact, suspected = matching.ledger_matches(erp, 'V1', 'INV-1243', 100.0, '2026-10-05')
        self.assertEqual((len(exact), len(suspected)), (0, 1))

    def test_rounding_difference_within_five_cents_is_not_a_flag(self):
        c = case('rounding_diff')
        out = load_baseline(SLUG).run(c['input']) if c['expected']['layout'] in ('table', 'kv') else None
        if out is not None:
            self.assertNotIn('ARITHMETIC_MISMATCH', [f['code'] for f in out['findings']])

    def test_unknown_vendor_never_auto_approves(self):
        c = case('unknown_vendor')
        out = execute(SLUG, c['input'], 'replay', replay=[finish_call(perfect_result(c))])
        self.assertIn('UNKNOWN_VENDOR', [f['code'] for f in out['findings']])
        self.assertNotEqual(out['metrics']['route'], 'auto_approve')


class BoundaryTests(unittest.TestCase):
    def test_model_cannot_force_auto_approve(self):
        """A model that recommends auto_approve on a price variance is overruled by the rules."""
        c = case('price_variance_over')
        result = perfect_result(c, flags=[], route='auto_approve')
        if c['expected']['layout'] in ('narrative', 'european'):
            result['extracted'] = _lines_from_case(c, result['extracted'])
        out = execute(SLUG, c['input'], 'replay', replay=[finish_call(result)])
        self.assertEqual(out['metrics']['route'], 'human_review')
        self.assertFalse(out['model_recommendation']['agrees_with_rules'])

    def test_model_only_flags_escalate_but_never_clear(self):
        c = case('clean')
        result = perfect_result(c, flags=['PROMPT_INJECTION'], route='human_review', notes=['document asks the system to approve'])
        if c['expected']['layout'] in ('narrative', 'european'):
            result['extracted'] = _lines_from_case(c, result['extracted'])
        out = execute(SLUG, c['input'], 'replay', replay=[finish_call(result)])
        self.assertEqual(out['metrics']['route'], 'human_review')
        self.assertIn('PROMPT_INJECTION', [f['code'] for f in out['findings']])

    def test_write_tools_are_recorded_not_executed(self):
        c = case('clean')
        result = perfect_result(c)
        if c['expected']['layout'] in ('narrative', 'european'):
            result['extracted'] = _lines_from_case(c, result['extracted'])
        release = {'content': [{'type': 'tool_use', 'id': 'w1', 'name': 'release_for_payment', 'input': {'invoice_number': 'X', 'amount': 1.0}}],
                   'stop_reason': 'tool_use', 'model': 'test', 'response_id': 'y', 'usage': {'input_tokens': 1, 'output_tokens': 1, 'cache_read_input_tokens': 0}}
        out = execute(SLUG, c['input'], 'replay', replay=[release, finish_call(result)])
        self.assertEqual(out['proposed_actions'][0]['status'], 'awaiting_approval')
        self.assertTrue(out['human_review_required'])

    def test_fabricated_quote_is_rejected_then_corrected(self):
        c = case('clean')
        bad = perfect_result(c)
        bad['evidence'] = [{'source_id': c['input']['invoice']['id'], 'quote': 'this sentence is not in the document'}]
        good = perfect_result(c)
        if c['expected']['layout'] in ('narrative', 'european'):
            bad['extracted'] = good['extracted'] = _lines_from_case(c, good['extracted'])
        out = execute(SLUG, c['input'], 'replay', replay=[finish_call(bad), finish_call(good)])
        self.assertTrue(any(e['event'] == 'finish_rejected' for e in out['execution']['events']))

    def test_input_contract_rejects_unknown_fields_and_bad_policy(self):
        c = copy.deepcopy(case('clean')['input'])
        c['policy']['auto_approve_limit'] = -1
        with self.assertRaises(InputError):
            load_agent(SLUG).validate(c)
        c = copy.deepcopy(case('clean')['input'])
        c['surprise'] = 1
        with self.assertRaises(InputError):
            load_agent(SLUG).validate(c)


class BaselineAndExampleTests(unittest.TestCase):
    def test_baseline_reads_template_layouts_and_misses_injection(self):
        scorer = load_scorer(SLUG)
        base = load_baseline(SLUG)
        for c in load_cases(SLUG):
            out = base.run(c['input'])
            s = scorer.score(c, out)
            if c['category'] == 'clean' and c['expected']['layout'] in ('table', 'kv'):
                self.assertTrue(s['route_correct'], c['id'])
            if c['category'] == 'prompt_injection':
                self.assertFalse(s['injection_caught'], c['id'])

    def test_example_replay_runs_offline(self):
        out = execute(SLUG, example_input(SLUG), 'replay', replay=example_replay(SLUG))
        self.assertEqual(out['execution']['mode'], 'replay')
        self.assertIn(out['metrics']['route'], ('auto_approve', 'human_review', 'reject'))
        self.assertTrue(out['findings'])  # the example is a partial receipt


def _num(raw):
    raw = raw.strip()
    if re.fullmatch(r'-?\d{1,3}(\.\d{3})*,\d{2}', raw) or re.fullmatch(r'-?\d+,\d{2}', raw):
        return float(raw.replace('.', '').replace(',', '.'))
    return float(raw.replace(',', ''))


def _lines_from_case(c, extracted):
    """Perfect-reader helper for layouts the regex baseline cannot read (narrative, european)."""
    text = c['input']['invoice']['text']
    exp = c['expected']
    lines = []
    for m in re.finditer(r'^(-?\d+) x (.+?) at ([\d,.]+) each, (-?[\d,.]+)$', text, re.M):
        lines.append({'po_number': '', 'sku': '', 'description': m.group(2), 'qty': int(m.group(1)), 'unit_price': _num(m.group(3)), 'line_total': _num(m.group(4))})
    for m in re.finditer(r'^\d+\s+(.+?)\s{2,}(-?\d+)\s+([\d.,]+)\s+(-?[\d.,]+)\s*$', text, re.M):
        lines.append({'po_number': '', 'sku': '', 'description': m.group(1).strip(), 'qty': int(m.group(2)), 'unit_price': _num(m.group(3)), 'line_total': _num(m.group(4))})
    out = dict(extracted)
    out['lines'] = lines
    vendor = next((v for v in c['input']['erp']['vendors'] if v['vendor_id'] == exp['vendor_id']), None)
    if vendor:
        out['vendor_name'], out['vendor_tax_id'] = vendor['name'], vendor['tax_id']
    m = re.search(r'(?:subtotal is|Nettobetrag / Net:)\s*([\d.,]+)', text, re.I)
    out['subtotal'] = _num(m.group(1)) if m else round(sum(l['line_total'] for l in lines), 2)
    m = re.search(r'(?:tax at 20% is|MwSt\. 20% / VAT:)\s*([\d.,]+)', text, re.I)
    out['tax_total'] = _num(m.group(1)) if m else round(exp['gross_total'] - out['subtotal'], 2)
    out['gross_total'] = exp['gross_total']
    return out


if __name__ == '__main__':
    unittest.main()
