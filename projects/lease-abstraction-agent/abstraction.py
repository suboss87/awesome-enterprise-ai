"""Deterministic lease abstraction rules: field taxonomy, grounding, precedence, date arithmetic, register, route.

The model reads each document in the lease package and states what that document says,
field by field, with a verbatim quote. This module decides. It checks that every quote is
in its document and that the stated value is visible in the quote, resolves each field by
document precedence (latest amendment > commencement letter for dates > original lease;
an estoppel certificate certifies and never amends), computes the expiration, the rent
schedule, the rent in effect and the critical-date register, applies the portfolio rules
and decides the route. The agent and the baseline call the same functions, so any
difference in results comes from the reading step.
"""
import calendar
import json
import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from enterprise_ai.common import InputError, day, integer, obj, rows, text

KINDS = ('lease', 'amendment', 'commencement_letter', 'estoppel')
ROUTES = ('ready_for_entry', 'conflicts_for_review', 'incomplete_documents')
ESCALATION_TYPES = ('fixed_pct', 'fixed_amount', 'cpi')
CAM_TYPES = ('gross', 'net', 'modified_gross')
CONSENT = ('not_unreasonably_withheld', 'sole_discretion', 'not_required')
SQM_TO_SQFT = Decimal('10.7639')
AREA_TOLERANCE = Decimal('0.005')  # sq ft and sq m figures within 0.5% describe the same premises
MIN_QUOTE = 12
CENT = Decimal('0.01')

VALUE_FORMS = {
    'landlord': 'landlord name as written',
    'tenant': 'tenant name as written',
    'premises': 'suite and building as written',
    'rentable_area': '<number> sq ft | <number> sq m, as written (one statement per unit stated)',
    'commencement_date': 'YYYY-MM-DD, or on_delivery when the document ties commencement to delivery without a date',
    'expiration_date': 'YYYY-MM-DD, only when the document states the date',
    'term_months': 'length of the initial term in months as digits (lease only)',
    'base_rent': '<amount> monthly | <amount> annual | <amount> psf annual: the first rent stated in prose (lease only)',
    'rent_step': 'YYYY-MM-DD: <amount> monthly|annual|psf annual, or month <n>: <amount> ...; one statement per row of a rent table or each dated rent in an amendment',
    'escalation': 'fixed_pct <pct> every <n> months | fixed_amount <amount> every <n> months | cpi | none',
    'renewal_option': '<count> x <n> months|years, notice <min> to <max> days|months, rent fmv|fixed; or notice at least <min> days|months; or none',
    'termination_option': 'YYYY-MM-DD, notice <n> days|months, fee <amount>; or none',
    'security_deposit': '<amount> | none',
    'cam': 'gross | net | modified_gross, followed by cap <pct> when increases are capped (e.g. net cap 5)',
    'holdover': '<pct>% | <multiple>x, as written (150% or 1.5x)',
    'assignment_consent': ' | '.join(CONSENT),
    'current_rent': '<amount>: monthly base rent certified as current (commencement letter or estoppel only)',
}
FIELDS = tuple(VALUE_FORMS)
FIELD_KINDS = {'term_months': ('lease',), 'base_rent': ('lease',), 'rent_step': ('lease', 'amendment'),
               'escalation': ('lease', 'amendment'), 'current_rent': ('commencement_letter', 'estoppel')}
DATE_FIELDS = ('commencement_date', 'expiration_date')
SCALARS = tuple(f for f in FIELDS if f not in ('rent_step', 'current_rent'))
REQUIRED = ('landlord', 'tenant', 'premises', 'rentable_area', 'commencement_date', 'expiration_date', 'base_rent', 'security_deposit',
            'cam', 'holdover', 'assignment_consent')
NOTICE_KINDS = ('renewal_notice_deadline', 'termination_notice_deadline')
DATE_KINDS = ('expiration', 'renewal_notice_opens', 'renewal_notice_deadline', 'termination_notice_deadline', 'termination_date', 'rent_step')
MODEL_FLAGS = ('PROMPT_INJECTION',)
READING_CODES = ('PROMPT_INJECTION', 'UNGROUNDED_FIELD', 'INVALID_FIELD')
REVIEW_CODES = ('UNRESOLVED_CONFLICT', 'ESCALATION_TYPE_NOT_ALLOWED', 'CAM_CAP_MISSING')

FINDING_TEXT = {
    'DATE_CONFLICT_RESOLVED_BY_AMENDMENT': ('info', 'Date set by a later document', 'A later amendment or the commencement letter governs; the earlier date is superseded.'),
    'FIELD_AMENDED': ('info', 'Term changed by an amendment', 'The amendment governs; the earlier value is superseded.'),
    'UNRESOLVED_CONFLICT': ('review', 'Documents disagree and precedence does not settle it', 'Same-rank documents disagree, a certificate disagrees with the governing value, or the term does not match the dates.'),
    'MISSING_FIELD': ('review', 'Required field has no grounded value', 'Obtain the missing document or clause before entry.'),
    'NOTICE_WINDOW_PASSED': ('urgent', 'Option notice deadline has passed', 'The notice deadline is before the review date while the option date is still ahead.'),
    'NOTICE_WINDOW_WITHIN_HORIZON': ('review', 'Option notice deadline inside the horizon', 'Calendar the deadline and its alert date.'),
    'ESCALATION_TYPE_NOT_ALLOWED': ('review', 'Rent escalation type not allowed by the portfolio rules', 'The lease admin lead approves the exception.'),
    'CAM_CAP_MISSING': ('review', 'Net lease without a cap on operating expense increases', 'The portfolio rules require a CAM cap.'),
    'FIGURE_NOT_IN_ABSTRACT': ('review', 'Summary contains a figure that is not in the abstract', 'The summary was withheld. Every date and number must come from the recorded abstract.'),
    'UNGROUNDED_FIELD': ('review', 'Stated field has no verbatim support', 'The statement was dropped: its quote is not in the document or does not show the value.'),
    'INVALID_FIELD': ('review', 'Stated field has an unreadable value or comes from the wrong document kind', 'The statement was dropped.'),
    'PROMPT_INJECTION': ('urgent', 'Document contains instructions aimed at the abstractor', 'Treat as suspicious; the rules ignore embedded instructions and a person reviews.'),
    'MODEL_DISAGREES': ('review', 'Model recommendation differs from the rules', 'The rules decide. The disagreement is logged for review.'),
    'SYSTEM_RECORD_DIFFERS': ('info', 'Lease system record differs from the documents', 'Update the lease system after approval.'),
}

# ---------------------------------------------------------------- input contract


def validate_lease(lease):
    obj(lease, ['id', 'documents'])
    text(lease['id'], 'lease id', 128)
    documents = rows(lease['documents'], 'lease.documents', 12, 1)
    seen = set()
    for doc in documents:
        obj(doc, ['id', 'kind', 'effective_date', 'text'])
        text(doc['id'], 'document id', 128)
        if doc['id'] in seen:
            raise InputError('Document ids must be unique')
        seen.add(doc['id'])
        if doc['kind'] not in KINDS:
            raise InputError('document.kind must be one of: ' + ', '.join(KINDS))
        day(doc['effective_date'])
        text(doc['text'], 'document text', 60000)
    if sum(d['kind'] == 'lease' for d in documents) > 1:
        raise InputError('A package holds at most one original lease')
    return lease


def validate_rules(rules):
    obj(rules, ['notice_lead_days_min', 'rent_escalation_types_allowed', 'cam_cap_required', 'critical_date_horizon_days', 'currency'])
    integer(rules['notice_lead_days_min'], 'notice_lead_days_min', 0, 730)
    integer(rules['critical_date_horizon_days'], 'critical_date_horizon_days', 1, 3650)
    allowed = rows(rules['rent_escalation_types_allowed'], 'rent_escalation_types_allowed', len(ESCALATION_TYPES))
    if any(t not in ESCALATION_TYPES for t in allowed) or len(set(allowed)) != len(allowed):
        raise InputError('rent_escalation_types_allowed must list distinct values of: ' + ', '.join(ESCALATION_TYPES))
    if type(rules['cam_cap_required']) is not bool:
        raise InputError('cam_cap_required must be true or false')
    if not isinstance(rules['currency'], str) or not re.fullmatch(r'[A-Z]{3}', rules['currency']):
        raise InputError('currency must be a three-letter code')
    return rules


SYSTEM_FIELDS = ('commencement_date', 'expiration_date', 'current_monthly_rent', 'security_deposit')


def validate_existing(existing):
    obj(existing, [], SYSTEM_FIELDS)
    for key, value in existing.items():
        if key in DATE_FIELDS:
            day(value)
        elif not isinstance(value, str) or not re.fullmatch(r'\d{1,10}\.\d\d|none', value):
            raise InputError(f'existing_abstract.{key} must be a decimal string with two places')
    return existing

# ---------------------------------------------------------------- date and money arithmetic


def add_months(start, months):
    """Calendar months; a day past the end of the target month clamps to its last day (Jan 31 + 1 = Feb 28/29)."""
    index = start.month - 1 + months
    year, month = start.year + index // 12, index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def term_end(start, months):
    """Last day of a term of `months` months that starts on `start`."""
    return add_months(start, months) - timedelta(days=1)


def months_between(start, end):
    """Whole months n with term_end(start, n) == end, or None."""
    guess = (end.year - start.year) * 12 + end.month - start.month
    return next((n for n in (guess - 1, guess, guess + 1) if n > 0 and term_end(start, n) == end), None)


def before(when, amount, unit):
    return add_months(when, -amount) if unit == 'months' else when - timedelta(days=amount)


def cents(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def monthly(rent, sqft):
    """Monthly rent from an amount and its basis; psf annual needs the rentable area in sq ft."""
    if rent['basis'] == 'monthly':
        return cents(rent['amount'])
    if rent['basis'] == 'annual':
        return cents(rent['amount'] / 12)
    return cents(rent['amount'] * sqft / 12) if sqft else None

# ---------------------------------------------------------------- values

AMOUNT = r'\$?(\d[\d,]*(?:\.\d{1,2})?)'
BASIS = r'(monthly|annual|psf annual)'


def _amount(raw):
    try:
        value = Decimal(raw.replace(',', ''))
    except InvalidOperation as exc:
        raise InputError('amount must be a number') from exc
    if not value.is_finite() or not Decimal(0) <= value <= Decimal('100000000'):
        raise InputError('amount out of range')
    return value


def _iso(raw):
    try:
        return day(raw)
    except InputError as exc:
        raise InputError('dates must be YYYY-MM-DD') from exc


def parse_value(field, value):
    """Normalize a stated value. Raises InputError when it is not in the form VALUE_FORMS gives."""
    raw = ' '.join(str(value).strip().split())
    low = raw.lower()
    if field in ('landlord', 'tenant', 'premises'):
        if not 2 <= len(raw) <= 300:
            raise InputError(f'{field} must be a name')
        return raw
    if field == 'rentable_area':
        m = re.fullmatch(r'(\d[\d,]*(?:\.\d+)?) ?(sq ?ft|square feet|sq ?m|square met(?:er|re)s)', low)
        if not m:
            raise InputError('rentable_area must be <number> sq ft or <number> sq m')
        amount, unit = _amount(m.group(1)), 'sq ft' if 'f' in m.group(2) else 'sq m'
        sqft = amount if unit == 'sq ft' else (amount * SQM_TO_SQFT).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        if not 0 < sqft <= 10000000:
            raise InputError('rentable_area out of range')
        return {'amount': amount, 'unit': unit, 'sqft': int(sqft)}
    if field == 'commencement_date':
        return 'on_delivery' if low == 'on_delivery' else _iso(raw)
    if field == 'expiration_date':
        return _iso(raw)
    if field == 'term_months':
        if not re.fullmatch(r'\d{1,4}', raw) or not 1 <= int(raw) <= 1200:
            raise InputError('term_months must be digits')
        return int(raw)
    if field in ('base_rent', 'rent_step'):
        m = re.fullmatch((r'(?:(\d{4}-\d{2}-\d{2})|month (\d{1,4})): ?' if field == 'rent_step' else '') + AMOUNT + ' ' + BASIS, low)
        if not m:
            raise InputError(f'{field} must follow: {VALUE_FORMS[field]}')
        groups = m.groups()
        rent = {'amount': _amount(groups[-2]), 'basis': groups[-1]}
        if field == 'rent_step':
            rent['from'] = _iso(groups[0]) if groups[0] else None
            rent['month'] = int(groups[1]) if groups[1] else None
            if rent['month'] is not None and rent['month'] < 1:
                raise InputError('rent_step month starts at 1')
        return rent
    if field == 'escalation':
        if low in ('none', 'cpi') or re.fullmatch(r'cpi every \d{1,3} months', low):
            return {'type': low.split()[0]}
        m = re.fullmatch(r'(fixed_pct|fixed_amount) ' + AMOUNT + r' every (\d{1,3}) months', low)
        if not m or int(m.group(3)) < 1:
            raise InputError('escalation must follow: ' + VALUE_FORMS['escalation'])
        return {'type': m.group(1), 'amount': _amount(m.group(2)), 'months': int(m.group(3))}
    if field == 'renewal_option':
        if low == 'none':
            return 'none'
        m = re.fullmatch(r'(\d{1,2}) x (\d{1,3}) (months?|years?), notice (?:(\d{1,4}) to (\d{1,4})|at least (\d{1,4})) (days|months), rent (fmv|fixed)', low)
        if not m:
            raise InputError('renewal_option must follow: ' + VALUE_FORMS['renewal_option'])
        count, length, unit, low_n, high_n, least, notice_unit, basis = m.groups()
        notice_min, notice_max = (int(low_n), int(high_n)) if low_n else (int(least), None)
        if int(count) < 1 or (notice_max is not None and notice_max <= notice_min):
            raise InputError('renewal_option notice window must run from the larger to the smaller lead time')
        return {'count': int(count), 'term': int(length), 'term_unit': 'years' if unit.startswith('year') else 'months',
                'term_months': int(length) * (12 if unit.startswith('year') else 1),
                'notice_min': notice_min, 'notice_max': notice_max, 'notice_unit': notice_unit, 'rent_basis': basis}
    if field == 'termination_option':
        if low == 'none':
            return 'none'
        m = re.fullmatch(r'(\d{4}-\d{2}-\d{2}), notice (\d{1,4}) (days|months), fee ' + AMOUNT, low)
        if not m:
            raise InputError('termination_option must follow: ' + VALUE_FORMS['termination_option'])
        return {'date': _iso(m.group(1)), 'notice': int(m.group(2)), 'notice_unit': m.group(3), 'fee': _amount(m.group(4))}
    if field == 'security_deposit':
        return 'none' if low == 'none' else _amount(re.sub(r'^\$', '', raw))
    if field == 'cam':
        m = re.fullmatch(r'(gross|net|modified_gross)(?: cap (\d{1,2}(?:\.\d+)?)%?)?', low)
        if not m:
            raise InputError('cam must follow: ' + VALUE_FORMS['cam'])
        return {'type': m.group(1), 'cap_pct': _amount(m.group(2)) if m.group(2) else None}
    if field == 'holdover':
        m = re.fullmatch(r'(\d{1,3}(?:\.\d+)?) ?(%|x)', low)
        if not m:
            raise InputError('holdover must be <pct>% or <multiple>x')
        number = _amount(m.group(1))
        return {'pct': number if m.group(2) == '%' else (number * 100).normalize(), 'stated': number}
    if field == 'assignment_consent':
        if low not in CONSENT:
            raise InputError('assignment_consent must be one of: ' + ', '.join(CONSENT))
        return low
    if field == 'current_rent':
        return _amount(re.sub(r'\s*monthly$', '', raw.lstrip('$')))
    raise InputError(f'Unknown field {field}')


def _visible(parsed, field):
    """(numbers, dates, words) that must appear in the quote for the value to count as read, not inferred."""
    numbers, dates, words = [], [], []
    if field == 'rentable_area':
        numbers.append(parsed['amount'])
    elif field in DATE_FIELDS:
        if parsed == 'on_delivery':
            words.append('deliver')
        else:
            dates.append(parsed)
    elif field == 'term_months':
        numbers.append(Decimal(parsed))
    elif field in ('base_rent', 'rent_step'):
        numbers.append(parsed['amount'])
        if parsed.get('from'):
            dates.append(parsed['from'])
        if parsed.get('month'):
            numbers.append(Decimal(parsed['month']))
    elif field == 'escalation':
        if parsed['type'] in ('fixed_pct', 'fixed_amount'):
            numbers.append(parsed['amount'])
        elif parsed['type'] == 'cpi':
            words.append('price index')
    elif field == 'renewal_option' and parsed != 'none':
        numbers += [Decimal(parsed['count']), Decimal(parsed['term']), Decimal(parsed['notice_min'])]
        numbers += [Decimal(parsed['notice_max'])] if parsed['notice_max'] is not None else []
    elif field == 'termination_option' and parsed != 'none':
        numbers += [Decimal(parsed['notice']), parsed['fee']]
        dates.append(parsed['date'])
    elif field in ('security_deposit', 'current_rent') and parsed != 'none':
        numbers.append(parsed)
    elif field == 'cam' and parsed['cap_pct'] is not None:
        numbers.append(parsed['cap_pct'])
    elif field == 'holdover':
        numbers.append(parsed['stated'])
    return numbers, dates, words


MONTHS = '|'.join(calendar.month_name[1:])
DATE_PATTERNS = (
    (re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b'), lambda m: (int(m[1]), int(m[2]), int(m[3]))),
    (re.compile(rf'\b({MONTHS}) (\d{{1,2}}), (\d{{4}})\b'), lambda m: (int(m[3]), list(calendar.month_name).index(m[1]), int(m[2]))),
    (re.compile(rf'\b(\d{{1,2}}) ({MONTHS}),? (\d{{4}})\b'), lambda m: (int(m[3]), list(calendar.month_name).index(m[2]), int(m[1]))),
    (re.compile(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b'), lambda m: (int(m[3]), int(m[1]), int(m[2]))),
)
NUMBER = re.compile(r'\d[\d,]*(?:\.\d+)?')


def figures(value, ignore=()):
    """Dates and numbers in a text. Dates in four written forms become date objects; other numbers become Decimals."""
    rest = str(value)
    for token in sorted(ignore, key=len, reverse=True):
        rest = rest.replace(token, ' ')
    dates = set()
    for pattern, parts in DATE_PATTERNS:
        for m in pattern.finditer(rest):
            try:
                dates.add(date(*parts(m)))
            except ValueError:
                continue
        rest = pattern.sub(' ', rest)
    numbers = set()
    for token in NUMBER.findall(rest):
        try:
            numbers.add(Decimal(token.replace(',', '')).normalize())
        except InvalidOperation:
            continue
    return dates, numbers


def ground(statements, documents):
    """Check each statement. Grounded = quote (MIN_QUOTE+ characters) is in that document, the value
    parses, the document kind may state the field, and the value's figures appear in the quote."""
    out, codes = [], []
    for item in statements:
        row = {k: str(item.get(k, '')) for k in ('document_id', 'field', 'value', 'quote')}
        row.update(grounded=False, problem=None)
        doc = documents.get(row['document_id'])
        if doc is None or row['field'] not in FIELDS or len(row['quote'].strip()) < MIN_QUOTE or row['quote'] not in doc['text']:
            row['problem'] = 'UNGROUNDED_FIELD'
        elif doc['kind'] not in FIELD_KINDS.get(row['field'], KINDS):
            row['problem'] = 'INVALID_FIELD'
        else:
            try:
                row['parsed'] = parse_value(row['field'], row['value'])
            except InputError:
                row['problem'] = 'INVALID_FIELD'
            else:
                numbers, dates, words = _visible(row['parsed'], row['field'])
                seen_dates, seen_numbers = figures(row['quote'])
                if (any(d not in seen_dates for d in dates) or any(n.normalize() not in seen_numbers for n in numbers)
                        or any(w not in row['quote'].lower() for w in words)):
                    row['problem'] = 'UNGROUNDED_FIELD'
                else:
                    row['grounded'] = True
        if row['problem']:
            codes.append(row['problem'])
        out.append(row)
    return out, list(dict.fromkeys(codes))

# ---------------------------------------------------------------- precedence


def rank(doc, field):
    """Precedence of a governing document for a field, or None when the document only certifies it."""
    if doc['kind'] == 'amendment':
        return (2, doc['effective_date'])
    if doc['kind'] == 'commencement_letter':
        return (1, doc['effective_date']) if field in DATE_FIELDS else None
    if doc['kind'] == 'lease':
        return (0, doc['effective_date'])
    return None


def same(field, a, b):
    if field == 'rentable_area':
        return abs(a['sqft'] - b['sqft']) <= AREA_TOLERANCE * max(a['sqft'], b['sqft'])
    if field == 'holdover':
        return a['pct'] == b['pct']
    return a == b


def _ref(row):
    return {'document_id': row['document_id'], 'value': row['value']}


def resolve(grounded, documents):
    """Winner per scalar field by precedence. Returns (fields {field: row}, conflicts)."""
    fields, conflicts = {}, []
    for field in SCALARS:
        items = [r for r in grounded if r['grounded'] and r['field'] == field]
        governing = [(rank(documents[r['document_id']], field), r) for r in items]
        certifying = [r for k, r in governing if k is None]
        governing = [(k, r) for k, r in governing if k is not None]
        if field == 'commencement_date' and any(r['parsed'] != 'on_delivery' for _, r in governing):
            governing = [(k, r) for k, r in governing if r['parsed'] != 'on_delivery']  # a placeholder, not a conflicting date
        if governing:
            top = max(k for k, _ in governing)
            leaders = [r for k, r in governing if k == top]
            if field == 'rentable_area':
                leaders.sort(key=lambda r: r['parsed']['unit'] != 'sq ft')
            winner = leaders[0]
            fields[field] = winner
            split = [r for r in leaders[1:] if not same(field, winner['parsed'], r['parsed'])]
            if split:
                conflicts.append({'field': field, 'kind': 'unresolved', 'winner': _ref(winner), 'others': [_ref(r) for r in split]})
            older = [r for k, r in governing if k < top and not same(field, winner['parsed'], r['parsed'])]
            if older:
                conflicts.append({'field': field, 'kind': 'resolved', 'winner': _ref(winner), 'others': [_ref(r) for r in older]})
        disagree = [r for r in certifying if field in fields and not same(field, fields[field]['parsed'], r['parsed'])]
        if disagree:
            conflicts.append({'field': field, 'kind': 'unresolved', 'winner': _ref(fields[field]), 'others': [_ref(r) for r in disagree]})
    return fields, conflicts


def _step_start(rent, start):
    if rent['from']:
        return rent['from']
    return add_months(start, rent['month'] - 1) if start else None


def rent_schedule(grounded, fields, documents, start, lease_end, sqft):
    """Rent steps [(from, monthly, document_id)], whether the schedule is complete, and amendment conflicts.

    The lease gives a table (rent_step rows) or a first rent with an escalation, expanded here up to
    the lease's own expiration. Each amendment, oldest first, replaces every step from its first
    dated row onward. CPI steps cannot be computed, so a CPI schedule stops after the first period."""
    steps, conflicts = [], []
    lease_rows = [r for r in grounded if r['grounded'] and r['field'] == 'rent_step' and documents[r['document_id']]['kind'] == 'lease']
    escalation = fields['escalation']['parsed'] if 'escalation' in fields else {'type': 'none'}
    if lease_rows:
        for r in lease_rows:
            begin, amount = _step_start(r['parsed'], start), monthly(r['parsed'], sqft)
            if begin and amount is not None:
                steps.append((begin, amount, r['document_id']))
    elif 'base_rent' in fields and start:
        amount, source = monthly(fields['base_rent']['parsed'], sqft), fields['base_rent']['document_id']
        if amount is not None:
            steps.append((start, amount, source))
            if escalation['type'] in ('fixed_pct', 'fixed_amount') and lease_end:
                i = 1
                while add_months(start, escalation['months'] * i) <= lease_end:
                    amount = cents(amount * (1 + escalation['amount'] / 100)) if escalation['type'] == 'fixed_pct' else cents(amount + escalation['amount'])
                    steps.append((add_months(start, escalation['months'] * i), amount, source))
                    i += 1
    steps = sorted(dict((s[0], s) for s in steps).values())
    amendments = sorted((d for d in documents.values() if d['kind'] == 'amendment'), key=lambda d: d['effective_date'])
    for doc in amendments:
        new = []
        for r in grounded:
            if r['grounded'] and r['field'] == 'rent_step' and r['document_id'] == doc['id']:
                begin, amount = _step_start(r['parsed'], start), monthly(r['parsed'], sqft)
                if begin and amount is not None:
                    new.append((begin, amount, doc['id']))
        if not new:
            continue
        new.sort()
        dropped = [s for s in steps if s[0] >= new[0][0]]
        steps = [s for s in steps if s[0] < new[0][0]] + new
        if dropped:
            conflicts.append({'field': 'rent_step', 'kind': 'resolved', 'winner': {'document_id': doc['id'], 'value': f'from {new[0][0].isoformat()}'},
                              'others': [{'document_id': s[2], 'value': f'{s[0].isoformat()}: {s[1]}'} for s in dropped]})
    return steps, escalation['type'] != 'cpi', conflicts


def rent_on(steps, complete, escalation, when, end):
    if not steps or (end and when > end):
        return None
    if not complete and when >= add_months(steps[0][0], escalation.get('months', 12)):
        return None
    current = steps[0]
    for step in steps:
        if step[0] <= when:
            current = step
    return current[1]

# ---------------------------------------------------------------- abstract, register, rules


def critical_dates(fields, expiration, steps, as_of, rules):
    """The register: every computed date, its status against the horizon, and an alert date for notice deadlines."""
    entries = []
    if expiration:
        entries.append(('expiration', expiration))
        renewal = fields.get('renewal_option', {}).get('parsed')
        if renewal and renewal != 'none':
            if renewal['notice_max'] is not None:
                entries.append(('renewal_notice_opens', before(expiration, renewal['notice_max'], renewal['notice_unit'])))
            entries.append(('renewal_notice_deadline', before(expiration, renewal['notice_min'], renewal['notice_unit'])))
    termination = fields.get('termination_option', {}).get('parsed')
    if termination and termination != 'none':
        entries.append(('termination_notice_deadline', before(termination['date'], termination['notice'], termination['notice_unit'])))
        entries.append(('termination_date', termination['date']))
    entries += [('rent_step', s[0]) for s in steps[1:]]
    horizon_end = as_of + timedelta(days=rules['critical_date_horizon_days'])
    register = []
    for kind, when in sorted(entries, key=lambda e: (e[1], DATE_KINDS.index(e[0]))):
        status = 'passed' if when < as_of else ('in_horizon' if when <= horizon_end else 'later')
        alert = (when - timedelta(days=rules['notice_lead_days_min'])).isoformat() if kind in NOTICE_KINDS else None
        register.append({'kind': kind, 'date': when.isoformat(), 'status': status, 'alert_date': alert})
    return register


def assess(lease, rules, as_of, statements, flags=()):
    """Ground, resolve, compute and route. Shared by the tools, the agent output and the baseline."""
    documents = {d['id']: d for d in lease['documents']}
    as_of = day(as_of) if isinstance(as_of, str) else as_of
    grounded, codes = ground(statements, documents)
    fields, conflicts = resolve(grounded, documents)
    start = fields.get('commencement_date', {}).get('parsed')
    start = start if isinstance(start, date) else None
    term = fields.get('term_months', {}).get('parsed')
    expiration_row = fields.get('expiration_date')
    expiration, expiration_source = (expiration_row['parsed'], expiration_row['document_id']) if expiration_row else (None, None)
    if expiration is None and start and term:
        expiration, expiration_source = term_end(start, term), 'computed'
    if term and start and expiration and (expiration_row is None or documents[expiration_row['document_id']]['kind'] != 'amendment') \
            and term_end(start, term) != expiration:
        conflicts.append({'field': 'term_months', 'kind': 'unresolved', 'winner': _ref(fields['term_months']),
                          'others': [{'document_id': expiration_source, 'value': f'{start.isoformat()} to {expiration.isoformat()}'}]})
    lease_expiration = [r['parsed'] for r in grounded if r['grounded'] and r['field'] == 'expiration_date' and documents[r['document_id']]['kind'] == 'lease']
    lease_end = lease_expiration[0] if lease_expiration else (term_end(start, term) if start and term else expiration)
    sqft = fields['rentable_area']['parsed']['sqft'] if 'rentable_area' in fields else None
    steps, complete, rent_conflicts = rent_schedule(grounded, fields, documents, start, lease_end, sqft)
    conflicts += rent_conflicts
    escalation = fields['escalation']['parsed'] if 'escalation' in fields else {'type': 'none'}
    for r in grounded:  # certified current rent: compare with the rent in effect on the certificate's date
        if r['grounded'] and r['field'] == 'current_rent':
            expected = rent_on(steps, complete, escalation, day(documents[r['document_id']]['effective_date']), expiration)
            if expected is not None and cents(r['parsed']) != expected:
                conflicts.append({'field': 'current_rent', 'kind': 'unresolved', 'winner': {'document_id': 'computed', 'value': str(expected)},
                                  'others': [_ref(r)]})
    register = critical_dates(fields, expiration, steps, as_of, rules)
    present = set(fields) - {'commencement_date', 'expiration_date', 'base_rent'}
    present |= {f for f, ok in (('commencement_date', start), ('expiration_date', expiration), ('base_rent', steps)) if ok}
    missing = [f for f in REQUIRED if f not in present]
    codes = [f for f in flags if f in MODEL_FLAGS] + codes
    for c in conflicts:
        codes.append('UNRESOLVED_CONFLICT' if c['kind'] == 'unresolved' else
                     'DATE_CONFLICT_RESOLVED_BY_AMENDMENT' if c['field'] in DATE_FIELDS else 'FIELD_AMENDED')
    codes += ['MISSING_FIELD'] if missing else []
    passed = [e for e in register if e['kind'] in NOTICE_KINDS and e['status'] == 'passed' and _option_alive(e, register, as_of)]
    within = [e for e in register if e['kind'] in NOTICE_KINDS and e['status'] == 'in_horizon']
    codes += (['NOTICE_WINDOW_PASSED'] if passed else []) + (['NOTICE_WINDOW_WITHIN_HORIZON'] if within else [])
    violations = []
    if escalation['type'] not in ('none',) + tuple(rules['rent_escalation_types_allowed']):
        violations.append('ESCALATION_TYPE_NOT_ALLOWED')
    cam = fields.get('cam', {}).get('parsed')
    if cam and cam['type'] != 'gross' and cam['cap_pct'] is None and rules['cam_cap_required']:
        violations.append('CAM_CAP_MISSING')
    codes = list(dict.fromkeys(codes + violations))
    deadlines = sorted(e['date'] for e in register if e['kind'] in NOTICE_KINDS and e['date'] >= as_of.isoformat())
    renewal_dates = {e['kind']: e['date'] for e in register if e['kind'].startswith('renewal_notice')}
    current = rent_on(steps, complete, escalation, as_of, expiration)
    key_dates = {'commencement_date': start.isoformat() if start else None, 'expiration_date': expiration.isoformat() if expiration else None,
                 'term_months': months_between(start, expiration) if start and expiration else None,
                 'current_monthly_rent': str(current) if current is not None else None,
                 'renewal_notice_opens': renewal_dates.get('renewal_notice_opens'), 'renewal_notice_deadline': renewal_dates.get('renewal_notice_deadline'),
                 'next_notice_deadline': deadlines[0] if deadlines else None}
    schedule = [{'from': s[0].isoformat(), 'to': (steps[i+1][0] - timedelta(days=1)).isoformat() if i+1 < len(steps) else
                 (expiration.isoformat() if complete and expiration else None), 'monthly_rent': str(s[1]), 'document_id': s[2]}
                for i, s in enumerate(steps)]
    return {'statements': grounded, 'fields': fields, 'conflicts': conflicts, 'missing': missing, 'codes': codes, 'violations': violations,
            'key_dates': key_dates, 'schedule': schedule, 'schedule_complete': complete, 'register': register,
            'expiration_source': expiration_source, 'route': route_for(codes)}


def _option_alive(entry, register, as_of):
    """A passed notice deadline matters only while its option date (expiration or termination date) is still ahead."""
    target = 'expiration' if entry['kind'] == 'renewal_notice_deadline' else 'termination_date'
    return any(e['kind'] == target and e['date'] >= as_of.isoformat() for e in register)


def route_for(codes):
    codes = set(codes)
    if codes & set(READING_CODES):
        return 'conflicts_for_review'
    if 'MISSING_FIELD' in codes:
        return 'incomplete_documents'
    return 'conflicts_for_review' if codes & set(REVIEW_CODES) else 'ready_for_entry'


def display(field, parsed):
    """JSON-friendly normalized value."""
    if isinstance(parsed, date):
        return parsed.isoformat()
    if isinstance(parsed, Decimal):
        return str(parsed)
    if isinstance(parsed, dict):
        return {k: display(k, v) for k, v in parsed.items() if v is not None}
    return parsed


def abstract_view(result):
    return {f: {'value': display(f, r['parsed']), 'document_id': r['document_id'], 'quote': r['quote']} for f, r in result['fields'].items()}

# ---------------------------------------------------------------- summary check and output


def check_summaries(drafts, core, ids):
    """Release a drafted summary only when every date and number in it is in the recorded abstract."""
    allowed_dates, allowed_numbers = figures(json.dumps(core, default=str), ids)
    out, codes = [], []
    for draft in drafts:
        narrative = str(draft.get('narrative', ''))
        dates, numbers = figures(narrative, ids)
        extra = sorted([d.isoformat() for d in dates - allowed_dates] + [str(n) for n in numbers - allowed_numbers])
        problem = 'FIGURE_NOT_IN_ABSTRACT' if extra else None
        if problem:
            codes.append(problem)
        out.append({'narrative': narrative, 'status': 'withheld' if problem else 'draft', 'problem': problem, 'unrecorded_figures': extra})
    return out, list(dict.fromkeys(codes))


def _same_text(a, b):
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except InvalidOperation:
        return str(a) == str(b)


def build_output(data, statements, flags, drafts, evidence, model_route=None):
    """Full decision and shared output shape for the agent and the baseline."""
    lease, rules = data['lease'], data['portfolio_rules']
    result = assess(lease, rules, data['as_of'], statements, flags)
    route, codes = result['route'], list(result['codes'])
    abstract = abstract_view(result)
    core = {'as_of': data['as_of'], 'abstract': {f: v['value'] for f, v in abstract.items()}, 'key_dates': result['key_dates'],
            'schedule': result['schedule'], 'register': result['register'], 'conflicts': result['conflicts']}
    ids = [lease['id']] + [d['id'] for d in lease['documents']]
    summaries, summary_codes = check_summaries(drafts, core, ids)
    changes = []
    current = {**result['key_dates'], 'security_deposit': abstract.get('security_deposit', {}).get('value')}
    for key, value in (data.get('existing_abstract') or {}).items():
        if current.get(key) is not None and not _same_text(current[key], value):
            changes.append({'field': key, 'system': value, 'documents': current[key]})
    codes += summary_codes + (['SYSTEM_RECORD_DIFFERS'] if changes else [])
    if model_route is not None and model_route != route:
        codes.append('MODEL_DISAGREES')
    detail_for = {'UNRESOLVED_CONFLICT': [c['field'] for c in result['conflicts'] if c['kind'] == 'unresolved'],
                  'DATE_CONFLICT_RESOLVED_BY_AMENDMENT': [c['field'] for c in result['conflicts'] if c['kind'] == 'resolved' and c['field'] in DATE_FIELDS],
                  'FIELD_AMENDED': [c['field'] for c in result['conflicts'] if c['kind'] == 'resolved' and c['field'] not in DATE_FIELDS],
                  'MISSING_FIELD': result['missing'],
                  'NOTICE_WINDOW_PASSED': [f"{e['kind']} {e['date']}" for e in result['register'] if e['kind'] in NOTICE_KINDS and e['status'] == 'passed'],
                  'NOTICE_WINDOW_WITHIN_HORIZON': [f"{e['kind']} {e['date']} (alert {e['alert_date']})" for e in result['register']
                                                   if e['kind'] in NOTICE_KINDS and e['status'] == 'in_horizon']}
    findings = []
    for code in dict.fromkeys(codes):
        severity, title, detail = FINDING_TEXT[code]
        items = list(dict.fromkeys(detail_for.get(code, [])))
        findings.append({'code': code, 'severity': severity, 'title': title, 'detail': detail + (f" Items: {', '.join(items)}." if items else ''),
                         'evidence_ids': [d['id'] for d in lease['documents']]})
    register = [e for e in result['register'] if e['status'] == 'in_horizon']
    released = [s for s in summaries if s['status'] == 'draft']
    actions = []
    if route == 'ready_for_entry':
        actions.append({'action': 'enter_abstract', 'owner': 'lease admin lead', 'status': 'awaiting_approval', 'lease_id': lease['id'],
                        'summary': released[-1]['narrative'] if released else None})
    elif route == 'conflicts_for_review':
        actions.append({'action': 'review_conflicts', 'owner': 'lease admin lead', 'status': 'queued', 'lease_id': lease['id'],
                        'reasons': [c for c in codes if c in READING_CODES + REVIEW_CODES]})
    else:
        actions.append({'action': 'request_documents', 'owner': 'lease administrator', 'status': 'draft', 'lease_id': lease['id'],
                        'missing_fields': result['missing']})
    if register:
        actions.append({'action': 'calendar_critical_dates', 'owner': 'lease administrator', 'status': 'awaiting_approval', 'dates': register})
    key = result['key_dates']
    summary = {'ready_for_entry': f"Lease {lease['id']} abstracted from {len(lease['documents'])} documents; expires {key['expiration_date']}. "
                                  f"{len(register)} critical dates in the next {rules['critical_date_horizon_days']} days. Ready for the lead's approval.",
               'conflicts_for_review': f"Lease {lease['id']} needs review: {', '.join(c for c in codes if c in READING_CODES + REVIEW_CODES)}.",
               'incomplete_documents': f"Lease {lease['id']} is incomplete: no grounded value for {', '.join(result['missing'])}."}[route]
    statements_out = [{k: r[k] for k in ('document_id', 'field', 'value', 'quote', 'grounded', 'problem')} for r in result['statements']]
    return {'project': 'lease-abstraction-agent', 'summary': summary,
            'metrics': {'route': route, 'statements': len(statements_out), 'ungrounded_statements': sum(not s['grounded'] for s in statements_out),
                        'fields_resolved': len(abstract), 'missing_fields': len(result['missing']),
                        'unresolved_conflicts': sum(c['kind'] == 'unresolved' for c in result['conflicts']),
                        'resolved_conflicts': sum(c['kind'] == 'resolved' for c in result['conflicts']),
                        'critical_dates_in_horizon': len(register), 'summaries_withheld': len(summaries) - len(released)},
            'findings': findings, 'actions': actions, 'human_review_required': True,
            'lease': {'id': lease['id'], 'documents': [{k: d[k] for k in ('id', 'kind', 'effective_date')} for d in lease['documents']]},
            'route': route, 'abstract': abstract, 'key_dates': key, 'rent_schedule': result['schedule'],
            'rent_schedule_complete': result['schedule_complete'], 'critical_dates': result['register'],
            'conflicts': result['conflicts'], 'missing_fields': result['missing'], 'rule_violations': result['violations'],
            'system_changes': changes, 'summaries': summaries, 'statements': statements_out, 'currency': rules['currency'], 'evidence': list(evidence)}
