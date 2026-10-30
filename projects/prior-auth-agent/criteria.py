"""Deterministic prior-authorization rules: evidence checks, criteria, eligibility, decision clock, route.

The model reads the clinical documents and records, per criterion, verbatim dated
quotes and the measured values it found. This module checks every quote against its
document, keeps only evidence inside each criterion's lookback window, computes
durations from dated entries and thresholds from printed values, checks code
pairing, eligibility, plan exclusions, site of service, peer-review triggers and
duplicates, runs the CMS-0057-F decision clock and decides the route. The agent and
the baseline call the same functions.

Approve-only. The routes are approve_proposed, nurse_review, medical_director_review
and information_requested. No route, action or tool expresses an adverse decision.
approve_proposed requires every applicable criterion met on verbatim, dated,
in-window evidence and no other finding except an at-risk clock. Anything else goes
to a person; a likely adverse outcome goes to the medical director, because only a
physician makes that determination.

Conventions:
  * Evidence window: [received date - lookback_days, received date], inclusive.
  * Duration: the longest chain of cited dates in which consecutive dates are at most
    max_gap_days apart; met when last - first >= min_days. A longer gap restarts it.
  * Threshold: every in-window value is compared with the policy threshold. Values that
    disagree on the outcome are a conflict and leave the criterion insufficient.
  * Presence and exclusion: met when the model claims it and cites in-window evidence
    from an allowed document kind; documented absence (met_claim false with a quote)
    is not met. An exclusion's evidence is the statement that rules it out.
  * Decision clock (CMS-0057-F, from 2026-01-01): expedited 72 hours, standard 7
    calendar days, both counted in calendar time from receipt. At risk below 24 hours.
"""
import operator
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from enterprise_ai.common import InputError

ROUTES = ('approve_proposed', 'nurse_review', 'medical_director_review', 'information_requested')
ACTIONS = ('approve', 'route_to_nurse', 'route_to_medical_director')
RECOMMENDATIONS = ACTIONS + ('request_information',)
ROUTE_OF = {'approve': 'approve_proposed', 'route_to_nurse': 'nurse_review',
            'route_to_medical_director': 'medical_director_review', 'request_information': 'information_requested'}
DOC_KINDS = ('clinical_note', 'imaging_report', 'lab_report', 'therapy_log', 'referral', 'fax_cover')
CRITERION_KINDS = ('duration', 'threshold', 'presence', 'exclusion', 'code_pairing')
SITES = ('office', 'freestanding_imaging', 'outpatient_hospital', 'ambulatory_surgery_center', 'inpatient', 'home')
VALUE_NAMES = ('bmi', 'hba1c')
OPS = {'>=': operator.ge, '>': operator.gt, '<=': operator.le, '<': operator.lt}
PEER_CONDITIONS = ('member_age_under', 'units_over', 'cpt_in')
STATUSES = ('met', 'not_met', 'insufficient', 'not_applicable')
EXPEDITED_HOURS, STANDARD_HOURS, AT_RISK_HOURS = 72, 168, Decimal(24)

FINDINGS = ['PROMPT_INJECTION', 'MEMBER_INELIGIBLE', 'SERVICE_EXCLUDED', 'DUPLICATE_REQUEST', 'CODE_PAIR_INVALID',
            'SITE_OF_SERVICE_MISMATCH', 'PEER_REVIEW_REQUIRED', 'CRITERION_NOT_MET', 'CRITERION_INSUFFICIENT_EVIDENCE',
            'EVIDENCE_DATE_OUTSIDE_WINDOW', 'CONFLICTING_DOCUMENTS', 'UNGROUNDED_CLAIM', 'SLA_AT_RISK']
MODEL_ONLY = {'PROMPT_INJECTION'}
TO_MEDICAL_DIRECTOR = {'PEER_REVIEW_REQUIRED', 'CRITERION_NOT_MET', 'SERVICE_EXCLUDED'}
MISSING_INFORMATION = {'CRITERION_INSUFFICIENT_EVIDENCE', 'EVIDENCE_DATE_OUTSIDE_WINDOW'}
NON_BLOCKING = {'SLA_AT_RISK'}

TEXT = {
    'PROMPT_INJECTION': ('urgent', 'A document contains instructions aimed at the review system', 'Treat the packet as suspicious; a nurse reviews it.'),
    'MEMBER_INELIGIBLE': ('review', 'Member not eligible on the requested start date', 'Verify eligibility with enrollment before clinical review.'),
    'SERVICE_EXCLUDED': ('review', 'Service excluded by the member\'s plan', 'Medical director review.'),
    'DUPLICATE_REQUEST': ('review', 'An approved authorization already covers this service and date', 'Nurse confirms the duplicate with the provider.'),
    'CODE_PAIR_INVALID': ('review', 'Procedure code not paired with a covered diagnosis', 'Nurse confirms the codes with the provider.'),
    'SITE_OF_SERVICE_MISMATCH': ('review', 'Requested site of service not allowed by the policy', 'Nurse discusses an allowed site with the provider.'),
    'PEER_REVIEW_REQUIRED': ('review', 'Policy requires physician review for this request', 'Medical director review.'),
    'CRITERION_NOT_MET': ('review', 'A coverage criterion is not met on the documents', 'Medical director review; the provider may offer peer-to-peer discussion.'),
    'CRITERION_INSUFFICIENT_EVIDENCE': ('info', 'A coverage criterion has no acceptable evidence', 'Request the missing documentation from the provider.'),
    'EVIDENCE_DATE_OUTSIDE_WINDOW': ('info', 'Cited evidence is outside the criterion\'s lookback window', 'Request current documentation.'),
    'CONFLICTING_DOCUMENTS': ('review', 'Documents disagree on a measured value', 'Nurse reconciles the documents.'),
    'UNGROUNDED_CLAIM': ('urgent', 'The reading step proposed approval that the evidence does not support', 'Nurse reviews the file; the proposal is not used.'),
    'SLA_AT_RISK': ('urgent', 'Decision clock has under 24 hours left', 'Review first in the queue.'),
}

_string = {'type': 'string'}
EVIDENCE_SCHEMA = {'type': 'object', 'properties': {
    'criterion_id': _string,
    'met_claim': {'type': 'boolean', 'description': 'Presence and exclusion criteria: true when the quotes show the criterion is met, '
                  'false when they show it is not. Duration and threshold criteria are computed from the dates and values.'},
    'quotes': {'type': 'array', 'description': 'Verbatim quotes, each with the date of the event it documents (YYYY-MM-DD). '
               'The date must be the document date or be printed in the quote.',
               'items': {'type': 'object', 'properties': {'source_id': _string, 'quote': _string, 'date': _string}}},
    'values': {'type': 'array', 'description': 'Threshold criteria only: each measured value printed in one of the quotes, '
               'with that quote\'s source_id and date. Record every value you find, including ones that disagree.',
               'items': {'type': 'object', 'properties': {'name': {'type': 'string', 'enum': list(VALUE_NAMES)},
                                                         'value': {'type': 'number'}, 'source_id': _string, 'date': _string}}},
}}

MONTHS = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December')
DENIAL = re.compile(
    r'\b(?:deny|denies|denied|denial|denying)\b[^.;\n]{0,80}?\b(?:request|authori[sz]ation|coverage|service|procedure|surgery|'
    r'imaging|mri|device|benefit|claim)s?\b'
    r'|\bnot medically necessary\b'
    r'|\b(?:request|authori[sz]ation|coverage|service|procedure)s? (?:is|are|was|were|has been|will be) '
    r'(?:denied|declined|rejected|not approved)\b', re.I)


# ---- parsing helpers -------------------------------------------------------------------------

def day(value, name='date'):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise InputError(f'{name} must be YYYY-MM-DD')
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise InputError(f'{name} must be a real date') from exc


def moment(value, name='datetime'):
    """An ISO 8601 date-time with a time zone, normalized to UTC."""
    if not isinstance(value, str) or not 16 <= len(value) <= 40:
        raise InputError(f'{name} must be an ISO 8601 date-time with a time zone')
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise InputError(f'{name} must be an ISO 8601 date-time with a time zone') from exc
    if parsed.tzinfo is None:
        raise InputError(f'{name} needs a time zone (for example 2026-10-30T14:00:00Z)')
    return parsed.astimezone(timezone.utc)


def dec(value):
    return Decimal(str(value))


def date_in_text(when, text):
    """True when the quote prints the date: ISO, US numeric, or written out."""
    month = MONTHS[when.month - 1]
    forms = (when.isoformat(), f'{when:%m/%d/%Y}', f'{when.month}/{when.day}/{when.year}',
             f'{month} {when.day}, {when.year}', f'{month[:3]} {when.day}, {when.year}', f'{when.day} {month} {when.year}')
    return any(form in text for form in forms)


def prints(quote, value):
    """True when the quote prints the value (41.3, 7, 7.0)."""
    v = dec(value)
    forms = {f'{v:f}', f'{v.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP):f}'}
    if v == v.to_integral_value():
        forms.add(str(int(v)))
    return any(re.search(r'(?<![\d.])' + re.escape(f) + r'(?![\d]|\.\d)', quote) for f in forms)


def contains_denial(text):
    """Language that states an adverse decision. Clinical negatives ("denies fever") do not match."""
    return bool(DENIAL.search(text or ''))


def criterion_by_id(policy, criterion_id):
    for criterion in policy['criteria']:
        if criterion['id'] == criterion_id:
            return criterion
    raise InputError(f'Unknown criterion {criterion_id}. Call get_criteria for the ids.')


# ---- recording evidence ------------------------------------------------------------------------

def normalize_record(data, raw):
    """Validate one criterion's evidence against the documents. Returns the stored record or raises InputError."""
    criterion = criterion_by_id(data['coverage_policy'], raw['criterion_id'])
    params, kind = criterion['params'], criterion['kind']
    if kind == 'code_pairing':
        raise InputError('Code pairing is checked from the request codes; record no evidence for it')
    docs = {d['id']: d for d in data['documents']}
    quotes, seen = [], set()
    for item in raw['quotes']:
        doc = docs.get(item['source_id'])
        if doc is None:
            raise InputError(f"Unknown document {item['source_id']}")
        if doc['kind'] not in params['evidence_kinds']:
            raise InputError(f"{criterion['id']} accepts evidence only from {', '.join(params['evidence_kinds'])}; "
                             f"{doc['id']} is a {doc['kind']}")
        quote = item['quote']
        if len(quote.strip()) < 8 or quote not in doc['text']:
            raise InputError(f"Quote is not verbatim in {doc['id']}; copy the text exactly, including OCR errors")
        when = day(item['date'], 'quote date')
        if item['date'] != doc['date'] and not date_in_text(when, quote):
            raise InputError(f"Quote date {item['date']} is neither the date of {doc['id']} ({doc['date']}) nor printed in the quote")
        if (doc['id'], quote, item['date']) not in seen:
            seen.add((doc['id'], quote, item['date']))
            quotes.append({'source_id': doc['id'], 'quote': quote, 'date': item['date']})
    if raw['met_claim'] and not quotes:
        raise InputError('met_claim=true needs at least one verbatim quote')
    values = []
    for item in raw['values']:
        if kind != 'threshold' or item['name'] != params['value_name']:
            raise InputError(f"{criterion['id']} takes no value named {item['name']}")
        if type(item['value']) not in (int, float) or not 0 < item['value'] < 1000:
            raise InputError('Values must be positive numbers')
        if not any(q['source_id'] == item['source_id'] and q['date'] == item['date'] and prints(q['quote'], item['value']) for q in quotes):
            raise InputError(f"Value {item['value']} must be printed in a recorded quote from {item['source_id']} dated {item['date']}")
        values.append({'name': item['name'], 'value': item['value'], 'source_id': item['source_id'], 'date': item['date']})
    if kind == 'threshold' and quotes and not values:
        raise InputError(f"Record the {params['value_name']} value printed in the quotes")
    return {'criterion_id': criterion['id'], 'met_claim': bool(raw['met_claim']), 'quotes': quotes, 'values': values}


# ---- criteria ------------------------------------------------------------------------------------

def longest_run(dates, max_gap_days):
    """(first, last) of the longest chain where consecutive dates are at most max_gap_days apart."""
    best = run = (dates[0], dates[0])
    for previous, current in zip(dates, dates[1:]):
        run = (run[0], current) if (current - previous).days <= max_gap_days else (current, current)
        if (run[1] - run[0]) > (best[1] - best[0]):
            best = run
    return best


def unpaired_codes(request, policy):
    service = request['service']
    pairs = {(cpt, icd) for cpt, icd in policy['valid_code_pairs']}
    return [cpt for cpt in service['cpt_codes'] if not any((cpt, icd) in pairs for icd in service['icd10_codes'])]


def evaluate_criterion(criterion, record, data):
    """Status of one criterion: met, not_met, insufficient or not_applicable, with the evidence used."""
    request, policy = data['request'], data['coverage_policy']
    params, kind = criterion['params'], criterion['kind']
    out = {'id': criterion['id'], 'kind': kind, 'text': criterion['text'], 'evidence': [], 'outside_window': [], 'conflict': False}
    applies = params.get('applies_to_cpt')
    if applies and not set(applies) & set(request['service']['cpt_codes']):
        return {**out, 'status': 'not_applicable', 'detail': 'Applies only to ' + ', '.join(applies)}
    if kind == 'code_pairing':
        bad = unpaired_codes(request, policy)
        return {**out, 'status': 'not_met' if bad else 'met',
                'detail': f"No covered diagnosis for {', '.join(bad)}" if bad else 'Every procedure code has a covered diagnosis'}
    end = moment(request['received_at']).date()
    start = end - timedelta(days=params['lookback_days'])
    quotes = record['quotes'] if record else []
    inside = [q for q in quotes if start <= day(q['date']) <= end]
    out['outside_window'] = [q for q in quotes if q not in inside]
    out['evidence'] = inside
    window = f'{start.isoformat()} to {end.isoformat()}'
    if kind == 'duration':
        dates = sorted({day(q['date']) for q in inside})
        if len(dates) < 2:
            return {**out, 'status': 'insufficient', 'detail': f'Fewer than two dated entries between {window}'}
        first, last = longest_run(dates, params['max_gap_days'])
        days = (last - first).days
        status = 'met' if days >= params['min_days'] else 'not_met'
        return {**out, 'status': status, 'detail': f"{days} days continuous ({first} to {last}, gaps of at most "
                                                   f"{params['max_gap_days']} days); policy requires {params['min_days']}"}
    if kind == 'threshold':
        values = [v for v in (record['values'] if record else [])]
        used = [v for v in values if start <= day(v['date']) <= end]
        out['outside_window'] += [v for v in values if v not in used]
        if not used:
            return {**out, 'status': 'insufficient', 'detail': f"No {params['value_name']} value between {window}"}
        test = OPS[params['op']]
        outcomes = {test(dec(v['value']), dec(params['threshold'])) for v in used}
        shown = ', '.join(f"{v['value']} ({v['source_id']}, {v['date']})" for v in used)
        if len(outcomes) > 1:
            return {**out, 'status': 'insufficient', 'conflict': True,
                    'detail': f"Values disagree on {params['value_name']} {params['op']} {params['threshold']}: {shown}"}
        return {**out, 'status': 'met' if True in outcomes else 'not_met',
                'detail': f"{params['value_name']} {shown}; policy requires {params['op']} {params['threshold']}"}
    if not inside:
        return {**out, 'status': 'insufficient', 'detail': f"No evidence from {', '.join(params['evidence_kinds'])} between {window}"}
    return {**out, 'status': 'met' if record['met_claim'] else 'not_met',
            'detail': ('Documented' if record['met_claim'] else 'Documents show the criterion is not met') + f' ({len(inside)} quotes)'}


def evaluate(data, records):
    return [evaluate_criterion(c, records.get(c['id']), data) for c in data['coverage_policy']['criteria']]


# ---- request-level checks -----------------------------------------------------------------------

def age_on(dob, when):
    return when.year - dob.year - ((when.month, when.day) < (dob.month, dob.day))


def administrative(data):
    """Eligibility, plan exclusions, site of service, peer-review triggers and duplicates: {code: detail}."""
    request, policy, plan = data['request'], data['coverage_policy'], data['plan']
    service = request['service']
    start = day(service['requested_start'])
    cpts = service['cpt_codes']
    found = {}
    window = plan['eligibility_dates']
    if not plan['benefit_active']:
        found['MEMBER_INELIGIBLE'] = 'The benefit is not active'
    elif not day(window['start']) <= start <= day(window['end']):
        found['MEMBER_INELIGIBLE'] = f"Requested start {start} is outside eligibility {window['start']} to {window['end']}"
    excluded = sorted(set(cpts) & set(plan['exclusions']))
    if excluded:
        found['SERVICE_EXCLUDED'] = 'Plan excludes ' + ', '.join(excluded)
    allowed = policy['site_of_service_rules']['allowed']
    if service['site_of_service'] not in allowed:
        found['SITE_OF_SERVICE_MISMATCH'] = f"Requested {service['site_of_service']}; policy allows {', '.join(allowed)}"
    reasons = []
    for rule in policy['requires_peer_review_if']:
        value = rule['value']
        if rule['condition'] == 'member_age_under' and age_on(day(request['member']['dob']), start) < value:
            reasons.append(f'member under {value}')
        elif rule['condition'] == 'units_over' and service['units'] > value:
            reasons.append(f"{service['units']} units requested (over {value})")
        elif rule['condition'] == 'cpt_in' and set(cpts) & set(value):
            reasons.append('code ' + ', '.join(sorted(set(cpts) & set(value))))
    if reasons:
        found['PEER_REVIEW_REQUIRED'] = 'Policy trigger: ' + '; '.join(reasons)
    for auth in data.get('authorization_history', []):
        if auth['status'] == 'approved' and set(cpts) & set(auth['cpt_codes']) and day(auth['valid_from']) <= start <= day(auth['valid_to']):
            found['DUPLICATE_REQUEST'] = f"Authorization {auth['auth_id']} approved for {', '.join(auth['cpt_codes'])}, valid {auth['valid_from']} to {auth['valid_to']}"
            break
    return found


def sla_clock(data):
    """CMS-0057-F decision clock in calendar time: expedited 72 hours, standard 7 days."""
    request = data['request']
    received, as_of = moment(request['received_at']), moment(data['as_of'])
    hours = EXPEDITED_HOURS if request['expedited'] else STANDARD_HOURS
    deadline = received + timedelta(hours=hours)
    remaining = (dec((deadline - as_of).total_seconds()) / 3600).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    return {'clock': 'expedited_72_hours' if request['expedited'] else 'standard_7_calendar_days',
            'received_at': received.isoformat().replace('+00:00', 'Z'), 'deadline': deadline.isoformat().replace('+00:00', 'Z'),
            'hours_remaining': float(remaining), 'at_risk': remaining < AT_RISK_HOURS}


# ---- decision ------------------------------------------------------------------------------------

def decide_route(codes):
    codes = set(codes)
    if codes & TO_MEDICAL_DIRECTOR:
        return 'medical_director_review'
    if codes - MISSING_INFORMATION - NON_BLOCKING:
        return 'nurse_review'
    if codes & MISSING_INFORMATION:
        return 'nurse_review' if 'SLA_AT_RISK' in codes else 'information_requested'
    return 'approve_proposed'


def assess(data, records, model_flags=(), approval_claims=()):
    """The decision. model_flags can only add model-only findings. approval_claims lists where the
    model asked for approval ('proposal', 'recommendation'); unsupported claims raise UNGROUNDED_CLAIM."""
    criteria = evaluate(data, records)
    found = administrative(data)
    by_status = {s: [c for c in criteria if c['status'] == s] for s in STATUSES}
    pairing = [c for c in by_status['not_met'] if c['kind'] == 'code_pairing']
    if pairing:
        found['CODE_PAIR_INVALID'] = pairing[0]['detail']
    clinical_not_met = [c for c in by_status['not_met'] if c['kind'] != 'code_pairing']
    if clinical_not_met:
        found['CRITERION_NOT_MET'] = '; '.join(f"{c['id']}: {c['detail']}" for c in clinical_not_met)
    if by_status['insufficient']:
        found['CRITERION_INSUFFICIENT_EVIDENCE'] = '; '.join(f"{c['id']}: {c['detail']}" for c in by_status['insufficient'])
    stale = [c for c in criteria if c['status'] in ('not_met', 'insufficient') and c['outside_window']]
    if stale:
        found['EVIDENCE_DATE_OUTSIDE_WINDOW'] = '; '.join(
            f"{c['id']}: evidence dated {', '.join(sorted({e['date'] for e in c['outside_window']}))}" for c in stale)
    conflicts = [c for c in criteria if c['conflict']]
    if conflicts:
        found['CONFLICTING_DOCUMENTS'] = '; '.join(f"{c['id']}: {c['detail']}" for c in conflicts)
    sla = sla_clock(data)
    if sla['at_risk']:
        found['SLA_AT_RISK'] = f"{sla['hours_remaining']} hours left on the {sla['clock'].replace('_', ' ')} clock (due {sla['deadline']})"
    for flag in model_flags:
        if flag in MODEL_ONLY:
            found.setdefault(flag, 'Reported by the reading step')
    if approval_claims and decide_route(found) != 'approve_proposed':
        found['UNGROUNDED_CLAIM'] = 'Approval requested by the model (' + ', '.join(approval_claims) + ') but the rules do not support it'
    codes = [c for c in FINDINGS if c in found]
    return {'route': decide_route(codes), 'findings': codes, 'details': found, 'criteria': criteria, 'sla': sla}


# ---- shared output ------------------------------------------------------------------------------

def missing_items(verdict):
    return [{'criterion_id': c['id'], 'text': c['text'], 'detail': c['detail']} for c in verdict['criteria'] if c['status'] == 'insufficient']


def template_request(data, verdict):
    items = missing_items(verdict)
    lines = [f"Prior authorization request {data['request']['id']}: to complete the clinical review we need the following documentation:"]
    lines += [f"{n}. {item['text']}" for n, item in enumerate(items, 1)]
    lines.append(f"Please send it before {verdict['sla']['deadline']}.")
    return '\n'.join(lines)


def information_request(data, verdict, draft):
    """The provider request for information_requested. A model draft is released only when it lists exactly
    the insufficient criteria and contains no adverse-decision language; otherwise the template is used."""
    if verdict['route'] != 'information_requested':
        return None
    items = missing_items(verdict)
    wanted = {i['criterion_id'] for i in items}
    status = 'not_drafted'
    if draft is not None:
        if set(draft['missing_criterion_ids']) != wanted:
            status = 'withheld_wrong_items'
        elif contains_denial(draft['message']):
            status = 'withheld_adverse_language'
        else:
            return {'missing_items': items, 'message': draft['message'], 'drafted_by': 'model', 'draft_status': 'released'}
    return {'missing_items': items, 'message': template_request(data, verdict), 'drafted_by': 'template', 'draft_status': status}


def build_output(data, verdict, draft, evidence, source):
    """Shared output for the agent and the baseline. source: 'model' or 'keyword-baseline'."""
    request = data['request']
    route, codes, sla = verdict['route'], verdict['findings'], verdict['sla']
    criteria = verdict['criteria']
    applicable = [c for c in criteria if c['status'] != 'not_applicable']
    findings = [{'code': c, 'severity': TEXT[c][0], 'title': TEXT[c][1], 'detail': verdict['details'][c] + '. ' + TEXT[c][2],
                 'evidence_ids': sorted({e['source_id'] for k in criteria for e in k['evidence']})} for c in codes]
    due = sla['deadline']
    missing = [c['id'] for c in criteria if c['status'] == 'insufficient']
    action = {
        'approve_proposed': {'action': 'approve', 'owner': 'UM nurse reviewer', 'status': 'awaiting_approval'},
        'nurse_review': {'action': 'nurse_review', 'owner': 'UM nurse reviewer', 'status': 'queued', 'findings': codes},
        'medical_director_review': {'action': 'medical_director_review', 'owner': 'Medical director', 'status': 'queued', 'findings': codes},
        'information_requested': {'action': 'request_additional_information', 'owner': 'UM nurse reviewer', 'status': 'awaiting_approval',
                                  'missing_criteria': missing},
    }[route]
    met = sum(1 for c in applicable if c['status'] == 'met')
    summary = {
        'approve_proposed': f'All {len(applicable)} applicable criteria met on cited, dated evidence. Approval proposed for nurse sign-off.',
        'nurse_review': f"Routed to a UM nurse reviewer: {', '.join(codes)}.",
        'medical_director_review': f"Routed to the medical director: {', '.join(codes)}. Only a physician makes an adverse determination.",
        'information_requested': 'Documentation requested from the provider for ' + ', '.join(missing) + '.',
    }[route] + f' Decision due {due}.'
    return {'project': 'prior-auth-agent', 'summary': summary,
            'metrics': {'route': route, 'criteria_met': met, 'criteria_applicable': len(applicable), 'finding_count': len(codes),
                        'sla_hours_remaining': sla['hours_remaining'], 'source': source},
            'findings': findings, 'actions': [{**action, 'request_id': request['id'], 'decision_due': due}],
            'criteria_status': {c['id']: c['status'] for c in criteria},
            'criteria': [{k: c[k] for k in ('id', 'kind', 'text', 'status', 'detail', 'evidence')} for c in criteria],
            'sla': sla, 'information_request': information_request(data, verdict, draft), 'evidence': evidence,
            'decision_boundary': 'Approve-only. The system proposes approval for nurse sign-off or routes the request to a nurse '
                                 'or the medical director. Only a physician makes an adverse determination.'}
