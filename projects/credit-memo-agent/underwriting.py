"""Deterministic underwriting rules: spread checks, period alignment, ratios, policy exceptions, route.

The model reads each statement and records a spread with verbatim quotes. This
module checks every spread figure against its statement, picks and aligns the
periods, computes every ratio, applies the credit policy and decides the route.
The model never states a figure: a memo may only use numbers this module computed
or the request and policy supplied. The agent and the baseline call the same functions.

Conventions:
  * Ratios are rounded half-up to two decimals before any policy comparison,
    the way credit policies state them (1.245x is 1.25x; 1.2449x is 1.24x).
  * EBITDA = revenue - COGS - operating expenses (which include D&A) + D + A.
    Adjusted EBITDA adds only add-backs the policy allows and the statement documents.
  * DSCR = (adjusted EBITDA - distributions) / (interest + current portion of
    long-term debt + proposed annual debt service). Global DSCR adds guarantor
    personal cash flow to the numerator.
  * Interim statements are annualized (x 12 / months covered) and tested like the year.
  * Leverage = (existing funded debt + proposed amount) / adjusted EBITDA.
  * LTV = amount / total appraised value; the limit is the appraisal-weighted policy
    maximum, so one low-advance item pulls the limit down for the whole package.
"""
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from enterprise_ai.common import InputError

ROUTES = ('ready_for_officer', 'exceptions_for_officer', 'insufficient_financials')
STATEMENT_KINDS = ('income_statement', 'balance_sheet', 'cash_flow', 'tax_return', 'interim')
FACILITY_TYPES = ('term_loan', 'revolver', 'cre_mortgage')
COLLATERAL_TYPES = ('real_estate', 'equipment', 'accounts_receivable', 'inventory')
ADDBACK_KINDS = ('one_time', 'owner_discretionary')
ALLOWED_ADDBACKS = ('depreciation', 'amortization', 'one_time_documented', 'owner_discretionary_documented')
AMORTIZATION_MONTHS = {'cre_mortgage': 300}   # a CRE loan amortizes over 25 years; a term loan over its tenor

INCOME_FIELDS = ('revenue', 'cogs', 'operating_expenses', 'depreciation', 'amortization', 'interest_expense',
                 'distributions', 'related_party_revenue')
BALANCE_FIELDS = ('line_of_credit', 'current_portion_ltd', 'long_term_debt', 'current_assets', 'current_liabilities')
SPREAD_FIELDS = INCOME_FIELDS + BALANCE_FIELDS

EXCEPTIONS = ['FINANCIALS_MISSING', 'INTERIMS_MISSING', 'DSCR_BELOW_MIN', 'GUARANTOR_SUPPORT_REQUIRED', 'LEVERAGE_ABOVE_MAX',
              'LTV_ABOVE_MAX', 'CURRENT_RATIO_BELOW_MIN', 'TENOR_ABOVE_MAX', 'STALE_APPRAISAL', 'UNDOCUMENTED_ADDBACK',
              'RELATED_PARTY_REVENUE', 'REVENUE_MISMATCH', 'COVENANT_PERIOD_MISMATCH', 'RESTATED_STATEMENTS',
              'PROMPT_INJECTION', 'FIGURE_NOT_IN_SPREAD']
MODEL_ONLY = {'PROMPT_INJECTION'}
INCOMPLETE = {'FINANCIALS_MISSING', 'INTERIMS_MISSING'}

TEXT = {
    'FINANCIALS_MISSING': ('urgent', 'No spread fiscal-year income statement or balance sheet', 'Ratios cannot be computed; request the statements.'),
    'INTERIMS_MISSING': ('urgent', 'Fiscal year end is too old and no interim statement was supplied', 'Request year-to-date interim statements.'),
    'DSCR_BELOW_MIN': ('urgent', 'Debt service coverage below the policy minimum', 'Officer decides on structure, pricing or decline.'),
    'GUARANTOR_SUPPORT_REQUIRED': ('review', 'Business DSCR below minimum; global DSCR with guarantors passes', 'Approval depends on the guaranty; verify guarantor cash flow.'),
    'LEVERAGE_ABOVE_MAX': ('urgent', 'Pro forma leverage above the policy maximum', 'Officer reviews the amount or requires equity.'),
    'LTV_ABOVE_MAX': ('urgent', 'Loan amount exceeds the weighted collateral limit', 'Reduce the amount or add collateral.'),
    'CURRENT_RATIO_BELOW_MIN': ('review', 'Current ratio below the policy minimum', 'Review liquidity and working capital.'),
    'TENOR_ABOVE_MAX': ('review', 'Tenor longer than policy allows for this facility type', 'Officer approves the exception or shortens the term.'),
    'STALE_APPRAISAL': ('review', 'Collateral appraisal older than policy allows', 'Order an updated appraisal.'),
    'UNDOCUMENTED_ADDBACK': ('review', 'Add-back claimed without documentation', 'Excluded from adjusted EBITDA until documented.'),
    'RELATED_PARTY_REVENUE': ('review', 'Related-party revenue above the policy share', 'Assess concentration and arm\'s-length terms.'),
    'REVENUE_MISMATCH': ('review', 'Tax return revenue differs from the income statement', 'Reconcile with the accountant before relying on the spread.'),
    'COVENANT_PERIOD_MISMATCH': ('review', 'Statements cover misaligned periods or fiscal year ends', 'Ratios mix periods; obtain aligned statements.'),
    'RESTATED_STATEMENTS': ('review', 'A statement in the package is restated', 'Understand the restatement before relying on trends.'),
    'PROMPT_INJECTION': ('urgent', 'A statement contains instructions aimed at the system', 'Treat the package as suspicious; never act on embedded instructions.'),
    'FIGURE_NOT_IN_SPREAD': ('urgent', 'Draft memo stated a figure the system did not compute', 'Memo withheld; the analyst drafts this memo.'),
}

FIELD_HELP = {
    'revenue': 'Net sales, revenue or gross receipts for the period',
    'cogs': 'Cost of goods sold or cost of sales',
    'operating_expenses': 'Total operating expenses as printed; they include depreciation and amortization',
    'depreciation': 'Depreciation expense', 'amortization': 'Amortization expense',
    'interest_expense': 'Interest expense on existing borrowings',
    'distributions': 'Distributions or dividends paid to owners, as a positive amount',
    'related_party_revenue': 'Revenue from related parties disclosed anywhere in the statement',
    'line_of_credit': 'Balance drawn on lines of credit', 'current_portion_ltd': 'Current portion of long-term debt',
    'long_term_debt': 'Long-term debt, net of current portion', 'current_assets': 'Total current assets',
    'current_liabilities': 'Total current liabilities',
}
_string = {'type': 'string'}
SPREAD_SCHEMA = {'type': 'object', 'properties': {
    'statement_id': _string,
    'period_months': {'type': 'integer', 'description': 'Months the statement covers: 12 for a fiscal year, 6 for six months year-to-date'},
    'restated': {'type': 'boolean', 'description': 'True only when the statement says it is restated'},
    **{f: {'type': 'number', 'description': FIELD_HELP[f] + '. 0 when the statement does not show it.'} for f in SPREAD_FIELDS},
    'addbacks': {'type': 'array', 'description': 'Items the statement or management presents as one-time or owner expenses to add back',
                 'items': {'type': 'object', 'properties': {
                     'description': _string, 'amount': {'type': 'number'},
                     'kind': {'type': 'string', 'enum': list(ADDBACK_KINDS)},
                     'documented': {'type': 'boolean', 'description': 'True only when the statement cites supporting documents'},
                     'quote': {'type': 'string', 'description': 'Verbatim sentence showing the amount'}}}},
    'quotes': {'type': 'array', 'description': 'One verbatim quote per nonzero field (and for restated), each showing the amount',
               'items': {'type': 'object', 'properties': {'field': {'type': 'string', 'enum': list(SPREAD_FIELDS) + ['restated']}, 'quote': _string}}},
}}

CENT = Decimal('0.01')
MONTHS = 'January|February|March|April|May|June|July|August|September|October|November|December'


def dec(value):
    return Decimal(str(value))


def q(value, places=2):
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _ratio(a, b):
    return q(a / b) if b > 0 else None


def _pct(part, whole):
    return q(part / whole * 100) if whole > 0 else None


def _shows(quote, value):
    """True when the quote prints the amount (whole units, cents, or thousands for large round amounts)."""
    forms = {f'{value:,.2f}', f'{value:.2f}'}
    if value == value.to_integral_value():
        forms |= {f'{int(value):,}', str(int(value))}
        if value >= 100000 and value % 1000 == 0:
            forms.add(f'{int(value) // 1000:,}')
    return any(re.search(r'(?<![\d,.])' + re.escape(f) + r'(?!\d|[.,]\d)', quote) for f in forms)


def normalize_spread(statement, raw):
    """Validate one recorded spread against its statement text. Returns the stored spread.

    Every nonzero figure needs a verbatim quote from the statement that prints it."""
    text = statement['text']
    months = raw['period_months']
    if type(months) is not int or not 1 <= months <= 12:
        raise InputError('period_months must be an integer from 1 to 12')
    values = {}
    for field in SPREAD_FIELDS:
        value = raw[field]
        if type(value) not in (int, float) or not 0 <= value <= 1e11:
            raise InputError(f'{field} must be a non-negative amount')
        values[field] = q(dec(value))
    quotes = {}
    for item in raw['quotes']:
        if item['field'] not in SPREAD_FIELDS + ('restated',):
            raise InputError(f"Unknown quote field {item['field']}")
        if len(item['quote'].strip()) < 4 or item['quote'] not in text:
            raise InputError(f"Quote for {item['field']} is not verbatim in statement {statement['id']}")
        quotes.setdefault(item['field'], []).append(item['quote'])
    missing = [f for f, v in values.items() if v and not any(_shows(qt, v) for qt in quotes.get(f, []))]
    if missing:
        raise InputError('Add a verbatim quote that prints the amount for: ' + ', '.join(missing))
    if raw['restated'] and 'restated' not in quotes:
        raise InputError('restated=true needs a verbatim quote saying so')
    addbacks = []
    for item in raw['addbacks']:
        amount = item['amount']
        if type(amount) not in (int, float) or not 0 < amount <= 1e11 or item['kind'] not in ADDBACK_KINDS:
            raise InputError('Each add-back needs a positive amount and a kind')
        amount = q(dec(amount))
        if item['quote'] not in text or not _shows(item['quote'], amount):
            raise InputError(f"Add-back quote must be verbatim in statement {statement['id']} and print the amount")
        addbacks.append({'description': item['description'], 'amount': amount, 'kind': item['kind'],
                         'documented': bool(item['documented']), 'quote': item['quote']})
    return {'statement_id': statement['id'], 'kind': statement['kind'], 'period_end': statement['period_end'],
            'fiscal_year_end': statement['fiscal_year_end'], 'period_months': months, 'restated': bool(raw['restated']),
            'values': values, 'addbacks': addbacks}


def select_periods(spreads):
    """Basis = latest fiscal-year income statement; balance = latest balance sheet;
    interim = latest interim ending after the basis year."""
    def latest(kind, after=''):
        rows = sorted((s for s in spreads.values() if s['kind'] == kind and s['period_end'] > after), key=lambda s: s['period_end'])
        return rows[-1] if rows else None
    basis = latest('income_statement')
    return basis, latest('balance_sheet'), latest('interim', basis['period_end']) if basis else None


def proposed_debt_service(facility):
    """Revolver: interest on the full commitment. Term and CRE: level monthly payment, rounded to cents, x 12."""
    amount, rate = dec(facility['amount']), dec(facility['rate']) / 100
    if facility['type'] == 'revolver':
        return q(amount * rate)
    n = AMORTIZATION_MONTHS.get(facility['type'], facility['tenor_months'])
    r = rate / 12
    payment = amount / n if r == 0 else amount * r / (1 - (1 + r) ** -n)
    return q(q(payment) * 12)


def addback_split(spread, allowed):
    accepted, rejected = [], []
    for item in spread['addbacks']:
        (accepted if item['documented'] and f"{item['kind']}_documented" in allowed else rejected).append(item)
    return accepted, rejected


def ebitda(spread):
    v = spread['values']
    return v['revenue'] - v['cogs'] - v['operating_expenses'] + v['depreciation'] + v['amortization']


def adjusted_ebitda(spread, allowed):
    v = spread['values']
    total = v['revenue'] - v['cogs'] - v['operating_expenses']
    total += (v['depreciation'] if 'depreciation' in allowed else 0) + (v['amortization'] if 'amortization' in allowed else 0)
    return total + sum((a['amount'] for a in addback_split(spread, allowed)[0]), Decimal(0))


def compute(data, spreads):
    """Every number the memo may use. Values are Decimals, or None when the inputs are missing."""
    request, policy = data['request'], data['credit_policy']
    facility, allowed = request['facility'], policy['add_back_rules']['allowed']
    basis, balance, interim = select_periods(spreads)
    r = {'basis_period_end': basis['period_end'] if basis else None, 'balance_sheet_date': balance['period_end'] if balance else None,
         'interim_period_end': interim['period_end'] if interim else None, 'interim_months': interim['period_months'] if interim else None}
    amount = dec(facility['amount'])
    r['proposed_debt_service'] = proposed_debt_service(facility)
    collateral = sum((dec(c['appraised_value']) for c in request['collateral']), Decimal(0))
    lendable = sum((dec(c['appraised_value']) * dec(policy['max_ltv'][c['type']]) for c in request['collateral']), Decimal(0))
    r['collateral_value'] = collateral
    r['ltv'] = _pct(amount, collateral)
    r['ltv_limit'] = q(lendable / collateral) if collateral else None
    guarantor_cf = sum((dec(g['personal_cash_flow']) for g in request['guarantors']), Decimal(0))
    r['guarantor_cash_flow'] = guarantor_cf
    keys = ('revenue', 'gross_profit', 'operating_income', 'ebitda', 'adjusted_ebitda', 'addbacks_accepted', 'distributions',
            'interest_expense', 'existing_debt_service', 'debt_service', 'dscr', 'global_dscr', 'interim_revenue_annualized',
            'interim_adjusted_ebitda_annualized', 'interim_debt_service', 'interim_dscr', 'interim_global_dscr', 'total_debt',
            'pro_forma_debt', 'leverage', 'current_assets', 'current_liabilities', 'current_ratio', 'related_party_pct',
            'gross_margin_pct', 'ebitda_margin_pct', 'tax_return_revenue', 'revenue_gap_pct')
    r.update({k: None for k in keys})
    if basis:
        v = basis['values']
        r['revenue'], r['interest_expense'] = v['revenue'], v['interest_expense']
        r['gross_profit'] = v['revenue'] - v['cogs']
        r['operating_income'] = r['gross_profit'] - v['operating_expenses']
        r['ebitda'], r['adjusted_ebitda'] = ebitda(basis), adjusted_ebitda(basis, allowed)
        r['addbacks_accepted'] = sum((a['amount'] for a in addback_split(basis, allowed)[0]), Decimal(0))
        r['distributions'] = max((s['values']['distributions'] for s in spreads.values() if s['period_end'] == basis['period_end']), default=Decimal(0))
        r['related_party_pct'] = _pct(v['related_party_revenue'], v['revenue'])
        r['gross_margin_pct'] = _pct(r['gross_profit'], v['revenue'])
        r['ebitda_margin_pct'] = _pct(r['ebitda'], v['revenue'])
        returns = [s for s in spreads.values() if s['kind'] == 'tax_return' and s['period_end'] == basis['period_end']]
        if returns:
            r['tax_return_revenue'] = returns[0]['values']['revenue']
            r['revenue_gap_pct'] = _pct(abs(r['tax_return_revenue'] - v['revenue']), v['revenue'])
    if balance:
        b = balance['values']
        r['total_debt'] = b['line_of_credit'] + b['current_portion_ltd'] + b['long_term_debt']
        r['pro_forma_debt'] = r['total_debt'] + amount
        r['current_assets'], r['current_liabilities'] = b['current_assets'], b['current_liabilities']
        r['current_ratio'] = _ratio(b['current_assets'], b['current_liabilities'])
    if basis and balance:
        cpltd = balance['values']['current_portion_ltd']
        r['existing_debt_service'] = r['interest_expense'] + cpltd
        r['debt_service'] = r['existing_debt_service'] + r['proposed_debt_service']
        cash = r['adjusted_ebitda'] - r['distributions']
        r['dscr'] = _ratio(cash, r['debt_service'])
        r['global_dscr'] = _ratio(cash + guarantor_cf, r['debt_service'])
        r['leverage'] = _ratio(r['pro_forma_debt'], r['adjusted_ebitda'])
        if interim:
            m, iv = interim['period_months'], interim['values']
            r['interim_revenue_annualized'] = q(iv['revenue'] * 12 / m)
            r['interim_adjusted_ebitda_annualized'] = q(adjusted_ebitda(interim, allowed) * 12 / m)
            r['interim_debt_service'] = q(iv['interest_expense'] * 12 / m) + cpltd + r['proposed_debt_service']
            cash_i = r['interim_adjusted_ebitda_annualized'] - q(iv['distributions'] * 12 / m)
            r['interim_dscr'] = _ratio(cash_i, r['interim_debt_service'])
            r['interim_global_dscr'] = _ratio(cash_i + guarantor_cf, r['interim_debt_service'])
    return r


def check_policy(data, spreads, ratios):
    """Return ({code: detail}) for every rule-based exception."""
    request, policy, as_of = data['request'], data['credit_policy'], date.fromisoformat(data['as_of'])
    facility = request['facility']
    basis, balance, interim = select_periods(spreads)
    found = {}
    if basis is None or balance is None:
        found['FINANCIALS_MISSING'] = 'Missing spread: ' + ', '.join(k for k, s in (('fiscal-year income statement', basis), ('balance sheet', balance)) if s is None)
    if basis is not None and interim is None:
        age = (as_of - date.fromisoformat(basis['period_end'])).days
        if age > policy['interim_required_if_fye_older_than_days']:
            found['INTERIMS_MISSING'] = f"Fiscal year ended {basis['period_end']}, {age} days before {data['as_of']}"
    min_dscr = q(dec(policy['min_dscr']))
    for label, dscr, global_dscr in (('Fiscal year', ratios['dscr'], ratios['global_dscr']),
                                     ('Annualized interim', ratios['interim_dscr'], ratios['interim_global_dscr'])):
        if dscr is None or dscr >= min_dscr:
            continue
        if global_dscr >= min_dscr:
            found.setdefault('GUARANTOR_SUPPORT_REQUIRED', f'{label} DSCR {dscr}x, global DSCR {global_dscr}x, minimum {min_dscr}x')
        else:
            found['DSCR_BELOW_MIN'] = f'{label} DSCR {dscr}x, global DSCR {global_dscr}x, minimum {min_dscr}x'
    if 'DSCR_BELOW_MIN' in found:
        found.pop('GUARANTOR_SUPPORT_REQUIRED', None)
    if basis and balance and (ratios['leverage'] is None or ratios['leverage'] > q(dec(policy['max_leverage']))):
        found['LEVERAGE_ABOVE_MAX'] = f"Pro forma leverage {ratios['leverage'] if ratios['leverage'] is not None else 'n/a (EBITDA not positive)'}x, maximum {policy['max_leverage']}x"
    if ratios['ltv'] is not None and ratios['ltv'] > ratios['ltv_limit']:
        found['LTV_ABOVE_MAX'] = f"LTV {ratios['ltv']}% against a weighted limit of {ratios['ltv_limit']}%"
    if ratios['current_ratio'] is not None and ratios['current_ratio'] < q(dec(policy['min_current_ratio'])):
        found['CURRENT_RATIO_BELOW_MIN'] = f"Current ratio {ratios['current_ratio']}x, minimum {policy['min_current_ratio']}x"
    if facility['tenor_months'] > policy['max_tenor_months'][facility['type']]:
        found['TENOR_ABOVE_MAX'] = f"Tenor {facility['tenor_months']} months, maximum {policy['max_tenor_months'][facility['type']]}"
    stale = [c for c in request['collateral'] if (as_of - date.fromisoformat(c['appraisal_date'])).days > policy['appraisal_max_age_days']]
    if stale:
        found['STALE_APPRAISAL'] = 'Appraised ' + ', '.join(f"{c['type']} on {c['appraisal_date']}" for c in stale)
    allowed = policy['add_back_rules']['allowed']
    undocumented = [a for s in (basis, interim) if s for a in addback_split(s, allowed)[1] if not a['documented']]
    if undocumented:
        found['UNDOCUMENTED_ADDBACK'] = 'Excluded: ' + '; '.join(f"{a['description']} ({a['amount']})" for a in undocumented)
    if ratios['related_party_pct'] is not None and ratios['related_party_pct'] > q(dec(policy['related_party_rule']['max_pct_of_revenue'])):
        found['RELATED_PARTY_REVENUE'] = f"Related-party revenue is {ratios['related_party_pct']}% of revenue"
    if ratios['revenue_gap_pct'] is not None and ratios['revenue_gap_pct'] > q(dec(policy['revenue_tolerance_pct'])):
        found['REVENUE_MISMATCH'] = f"Tax return revenue {ratios['tax_return_revenue']} differs by {ratios['revenue_gap_pct']}%"
    year_ends = sorted({s['fiscal_year_end'] for s in spreads.values()})
    aligned = {basis['period_end'] if basis else None, interim['period_end'] if interim else None}
    if len(year_ends) > 1:
        found['COVENANT_PERIOD_MISMATCH'] = 'Fiscal year ends differ across statements: ' + ', '.join(year_ends)
    elif balance and basis and balance['period_end'] not in aligned:
        found['COVENANT_PERIOD_MISMATCH'] = f"Balance sheet dated {balance['period_end']} does not match an income period end"
    restated = [s['statement_id'] for s in spreads.values() if s['restated']]
    if restated:
        found['RESTATED_STATEMENTS'] = 'Restated: ' + ', '.join(sorted(restated))
    return found


def decide_route(codes):
    if set(codes) & INCOMPLETE:
        return 'insufficient_financials'
    return 'exceptions_for_officer' if codes else 'ready_for_officer'


def assess(data, spreads, model_flags=(), memo=None):
    """The decision. model_flags can only add model-only exceptions; a memo with an
    unsupported figure is withheld and raises FIGURE_NOT_IN_SPREAD."""
    ratios = compute(data, spreads)
    found = check_policy(data, spreads, ratios)
    for flag in model_flags:
        if flag in MODEL_ONLY:
            found.setdefault(flag, 'Reported by the reading step')
    unsupported = unsupported_figures(memo_text(memo), allowed_figures(data, spreads, ratios)) if memo else []
    if unsupported:
        found['FIGURE_NOT_IN_SPREAD'] = 'Not computed by the system: ' + ', '.join(unsupported[:8])
    codes = [c for c in EXCEPTIONS if c in found]
    return {'route': decide_route(codes), 'exceptions': codes, 'details': found, 'ratios': ratios,
            'memo_unsupported': unsupported}


# ---- memo figure control -------------------------------------------------------------------

FIGURE = re.compile(r'(?<![\w.,/-])(\$?)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?:\s?(million|thousand|mm|m|k|x|%))?(?![\w-])', re.I)
DATES = re.compile(rf'\b\d{{4}}-\d{{2}}-\d{{2}}\b|\b(?:{MONTHS})\.? \d{{1,2}}, \d{{4}}\b|\b\d{{1,2}}/\d{{1,2}}/\d{{2,4}}\b')


def memo_text(memo):
    return '\n'.join(str(v) for v in memo.values()) if isinstance(memo, dict) else str(memo or '')


def allowed_figures(data, spreads, ratios):
    """Numbers a memo may state: the request, the policy, the recorded spreads and the computed ratios."""
    request, policy = data['request'], data['credit_policy']
    values = [request['facility']['amount'], request['facility']['rate'], request['facility']['tenor_months']]
    values += [c['appraised_value'] for c in request['collateral']]
    values += [g[k] for g in request['guarantors'] for k in ('net_worth', 'liquidity', 'personal_cash_flow')]
    values += [policy['min_dscr'], policy['max_leverage'], policy['min_current_ratio'], policy['appraisal_max_age_days'],
               policy['interim_required_if_fye_older_than_days'], policy['revenue_tolerance_pct'],
               policy['related_party_rule']['max_pct_of_revenue'], *policy['max_ltv'].values(), *policy['max_tenor_months'].values()]
    for spread in spreads.values():
        values += list(spread['values'].values()) + [a['amount'] for a in spread['addbacks']] + [spread['period_months']]
    values += [v for v in ratios.values() if isinstance(v, (Decimal, int))]
    plain, thousands, millions = set(), set(), set()
    for raw in values:
        v = abs(dec(raw))
        plain |= {v, q(v, 0), q(v, 1), q(v, 2)}
        if v >= 1000:
            thousands |= {q(v / 1000, 0), q(v / 1000, 1)}
        if v >= 100000:
            millions |= {q(v / 1000000, 1), q(v / 1000000, 2)}
    return plain, thousands, millions


def unsupported_figures(text, allowed):
    """Figures in the text that match no allowed number. Dates, years and small counts are not figures."""
    plain, thousands, millions = allowed
    misses = []
    for m in FIGURE.finditer(DATES.sub(' ', text)):
        dollar, whole, frac, unit = m.group(1), m.group(2), m.group(3) or '', (m.group(4) or '').lower()
        value = Decimal(whole.replace(',', '') + frac)
        if not (dollar or frac or unit or ',' in whole) and (value <= 12 or 1900 <= value <= 2100):
            continue
        pool = millions if unit in ('million', 'mm', 'm') else thousands if unit in ('thousand', 'k') else plain
        if value not in pool:
            misses.append(m.group(0).strip())
    return misses


# ---- shared output -------------------------------------------------------------------------

def to_json(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: to_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_json(v) for v in value]
    return value


def build_output(data, verdict, spreads, memo, evidence, memo_source):
    """Shared output for the agent and the baseline. memo_source: 'model' or 'template'."""
    route, codes, ratios = verdict['route'], verdict['exceptions'], verdict['ratios']
    source_ids = [s['id'] for s in data['statements']]
    findings = [{'code': c, 'severity': TEXT[c][0], 'title': TEXT[c][1], 'detail': verdict['details'][c] + '. ' + TEXT[c][2],
                 'evidence_ids': source_ids} for c in codes]
    if memo is None:
        memo_status, released = 'not_drafted', None
    elif verdict['memo_unsupported']:
        memo_status, released = 'withheld', None
    else:
        memo_status, released = f'drafted_by_{memo_source}', memo
    request_id = data['request']['id']
    if route == 'ready_for_officer':
        actions = [{'action': 'submit_to_credit_committee', 'owner': 'Credit officer', 'status': 'awaiting_approval', 'request_id': request_id}]
    elif route == 'exceptions_for_officer':
        actions = [{'action': 'officer_exception_review', 'owner': 'Credit officer', 'status': 'queued', 'request_id': request_id, 'exceptions': codes}]
    else:
        actions = [{'action': 'request_financials', 'owner': 'Credit analyst', 'status': 'queued', 'request_id': request_id,
                    'exceptions': [c for c in codes if c in INCOMPLETE]}]
    if memo_status == 'withheld':
        actions.append({'action': 'analyst_drafts_memo', 'owner': 'Credit analyst', 'status': 'queued'})
    summary = {'ready_for_officer': 'Spread complete, ratios within policy, no exceptions. Ready for the credit officer.',
               'exceptions_for_officer': f"Policy exceptions for the credit officer: {', '.join(codes)}.",
               'insufficient_financials': f"Financials insufficient: {', '.join(c for c in codes if c in INCOMPLETE)}."}[route]
    pick = ('dscr', 'global_dscr', 'interim_dscr', 'leverage', 'ltv', 'ltv_limit', 'current_ratio', 'revenue', 'ebitda',
            'adjusted_ebitda', 'total_debt', 'debt_service')
    return {'project': 'credit-memo-agent', 'summary': summary,
            'metrics': {'route': route, 'exception_count': len(codes), **to_json({k: ratios[k] for k in pick})},
            'findings': findings, 'actions': actions, 'exceptions': codes, 'ratios': to_json(ratios),
            'spread': to_json(spreads), 'memo': released, 'memo_status': memo_status,
            'memo_unsupported_figures': verdict['memo_unsupported'], 'evidence': evidence,
            'decision_boundary': 'No approve or decline recommendation. A credit officer decides; the committee approves.'}
