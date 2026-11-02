"""Rules-only baseline: a spreading template that parses tabular statements, plus a template memo.

This is what a credit team builds without a model: regexes for the line labels its
borrowers' accountants usually print ("Net sales", "Total current liabilities",
"Distributions to members"), a few note patterns, and a fill-in-the-blanks memo.
Accountant letters with the numbers in prose produce no spread, so those packages
come out as insufficient financials. Embedded instructions are invisible to it.
The same `underwriting.py` rules compute the ratios and decide the route.
"""
import importlib.util
import re
from pathlib import Path

from enterprise_ai.common import InputError

_here = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('credit_underwriting_b', _here/'underwriting.py')
uw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(uw)
_aspec = importlib.util.spec_from_file_location('credit_agent_b', _here/'agent.py')
agent_module = importlib.util.module_from_spec(_aspec)
_aspec.loader.exec_module(agent_module)

LABELS = {
    'revenue': r'(?:Net sales|Revenues?|Total revenues|1a Gross receipts or sales)',
    'cogs': r'(?:2\s+)?Cost of (?:goods sold|sales)',
    'operating_expenses': r'(?:Total )?Operating expenses',
    'interest_expense': r'(?:Interest expense|13 Interest)',
    'distributions': r'Distributions to (?:members|shareholders|owners)',
    'line_of_credit': r'Line of credit',
    'current_portion_ltd': r'Current portion of long-term debt',
    'long_term_debt': r'Long-term debt, net of current portion',
    'current_assets': r'Total current assets',
    'current_liabilities': r'Total current liabilities',
}
MONTH_WORDS = {'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11}
AMOUNT = r'\(?([\d,]{4,})\)?'


def _amount(raw):
    return int(raw.replace(',', ''))


def spread_statement(statement):
    """Template spread of one statement, or None when no table row matches."""
    text = statement['text']
    raw = {f: 0 for f in uw.SPREAD_FIELDS}
    quotes = []
    for field, label in LABELS.items():
        m = re.search(rf'^\s*{label}\s{{2,}}{AMOUNT}\s*$', text, re.M | re.I)
        if m:
            raw[field] = _amount(m.group(1))
            quotes.append({'field': field, 'quote': m.group(0).strip()})
    if not quotes:
        return None
    for field in ('depreciation', 'amortization'):
        m = re.search(rf'^\d+\. .*?\b{field} of ([\d,]+)', text, re.M | re.I)
        if m:
            raw[field] = _amount(m.group(1))
            quotes.append({'field': field, 'quote': m.group(0)})
    m = re.search(r'^\d+\. Related party transactions:.*?totaled ([\d,]+)', text, re.M)
    if m:
        raw['related_party_revenue'] = _amount(m.group(1))
        quotes.append({'field': 'related_party_revenue', 'quote': m.group(0)})
    m = re.search(r'^.*\brestated\b.*$', text, re.M | re.I)
    raw['restated'] = bool(m)
    if m:
        quotes.append({'field': 'restated', 'quote': m.group(0)})
    m = re.search(r'For the (\w+) months ended', text)
    raw['period_months'] = MONTH_WORDS.get(m.group(1).lower(), 12) if m else 12
    raw['addbacks'] = []
    for line in re.findall(r'^\d+\. .*(?:one-time|non-recurring|adding back|added back).*$', text, re.M | re.I):
        amount = re.search(r'([\d,]{5,})', line)
        if amount:
            raw['addbacks'].append({'description': line[3:80], 'amount': _amount(amount.group(1)),
                                    'kind': 'owner_discretionary' if 'owner' in line.lower() else 'one_time',
                                    'documented': not re.search(r'no supporting|no engagement letter|not provided', line, re.I), 'quote': line})
    raw['quotes'] = quotes
    raw['statement_id'] = statement['id']
    try:
        return uw.normalize_spread(statement, raw)
    except InputError:
        return None


def _fmt(value, suffix=''):
    if value is None:
        return 'n/a'
    return (f'{value:,.0f}' if abs(value) >= 1000 else f'{value}') + suffix


def template_memo(data, verdict):
    """Fill-in-the-blanks memo. Every figure comes from the request or the computed ratios."""
    r, request = verdict['ratios'], data['request']
    f = request['facility']
    return {
        'borrower': f"{request['borrower']}.",
        'facility': f"{f['type'].replace('_', ' ').title()} of {f['amount']:,} at {f['rate']}% for {f['tenor_months']} months. Purpose: {f['purpose']}.",
        'financial_analysis': f"Revenue {_fmt(r['revenue'])}; EBITDA {_fmt(r['ebitda'])}; adjusted EBITDA {_fmt(r['adjusted_ebitda'])}; "
                              f"DSCR {_fmt(r['dscr'], 'x')}; global DSCR {_fmt(r['global_dscr'], 'x')}; leverage {_fmt(r['leverage'], 'x')}; "
                              f"current ratio {_fmt(r['current_ratio'], 'x')}.",
        'collateral': f"LTV {_fmt(r['ltv'], '%')} against a weighted limit of {_fmt(r['ltv_limit'], '%')}.",
        'guarantors': '; '.join(f"{g['name']}: personal cash flow {g['personal_cash_flow']:,}" for g in request['guarantors']) or 'None.',
        'risks': ', '.join(verdict['exceptions']) or 'No policy exceptions.',
        'mitigants': 'To be completed by the analyst.',
        'policy_exceptions': '; '.join(verdict['details'][c] for c in verdict['exceptions']) or 'None.',
    }


def run(data):
    agent_module.validate(data)
    spreads = {}
    for statement in data['statements']:
        spread = spread_statement(statement)
        if spread is not None:
            spreads[statement['id']] = spread
    verdict = uw.assess(data, spreads)
    memo = template_memo(data, verdict)
    verdict = uw.assess(data, spreads, memo=memo)
    output = uw.build_output(data, verdict, spreads, memo, [], 'template')
    output['baseline'] = 'regex-table-spread'
    return output
