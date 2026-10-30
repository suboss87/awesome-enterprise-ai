"""Deterministic playbook rules: clause map, term grounding, deviations, risk tier, route, redline check.

The model reads the contract and states each term with a verbatim quote. This module
decides. It splits the text into numbered clauses, checks that every quote exists in the
contract and finds its clause, parses each stated value, compares it with the playbook
position for its topic, assigns a risk tier (acceptable, counsel, walk_away) and computes
the route. It accepts a proposed redline only when its text is the playbook fallback for
a topic that needs one. The agent and the baseline call the same functions, so any
difference in results comes from the reading step.
"""
import re
from decimal import Decimal, InvalidOperation

from enterprise_ai.common import InputError, obj, rows, text

CONTRACT_TYPES = ('NDA', 'MSA')
PAPERS = ('ours', 'theirs')
ROLES = ('legal_ops', 'sales', 'counsel')
ROUTES = ('approve_standard', 'counsel_review', 'walk_away')
TOPICS = ('mutuality', 'term', 'exclusions', 'residuals', 'non_solicit', 'governing_law', 'venue', 'auto_renewal',
          'liability_cap', 'ip_indemnity')
REQUIRED = {'NDA': ('mutuality', 'term', 'exclusions', 'governing_law'),
            'MSA': ('liability_cap', 'ip_indemnity', 'governing_law')}
NUMBER = (int, float)
RULE_KEYS = {
    'mutuality': {'require_mutual': bool},
    'term': {'preferred_months': int, 'max_months': int},
    'exclusions': {},
    'residuals': {'if_present': str},
    'non_solicit': {'if_present': str},
    'governing_law': {'allowed': list},
    'venue': {'must_match_governing_law': bool},
    'auto_renewal': {'min_notice_days': int},
    'liability_cap': {'preferred_multiple': NUMBER, 'min_multiple': NUMBER, 'walk_away_below': NUMBER},
    'ip_indemnity': {'require_uncapped': bool},
}
VALUE_FORMS = {
    'mutuality': 'mutual | one_way (one_way when only one party is bound, whatever the title says)',
    'term': 'confidentiality period in months as digits (5 years = 60), or perpetual',
    'exclusions': 'standard | overbroad (overbroad when any exclusion or carve-out lets the recipient escape the duty)',
    'residuals': 'present (any right to use information retained in memory)',
    'non_solicit': 'present (any restriction on soliciting, hiring or engaging the other side\'s staff)',
    'governing_law': 'state or country whose law governs, e.g. New York, Delaware, England and Wales',
    'venue': 'state or country of the courts with jurisdiction, e.g. New York, Singapore',
    'auto_renewal': 'none | no_notice | notice days as digits (the non-renewal notice window)',
    'liability_cap': 'general cap on each party\'s total liability as a multiple of 12 months of fees, e.g. 2, 1, 0.5, 0.25, or uncapped',
    'ip_indemnity': 'uncapped | capped (capped when the supplier IP indemnity is subject to the liability cap)',
}
MODEL_FLAGS = ('PROMPT_INJECTION',)
ESCALATING = ('PROMPT_INJECTION', 'UNGROUNDED_TERM', 'INVALID_TERM')
MIN_QUOTE = 12
JURISDICTION_ALIASES = {'ny': 'new york', 'england': 'england and wales', 'english': 'england and wales',
                        'uk': 'england and wales', 'london': 'england and wales', 'manhattan': 'new york'}

FINDING_TEXT = {
    'WALK_AWAY_TERM': ('urgent', 'Term beyond the walk-away line', 'The playbook does not allow this term at any price. Counsel decides whether to continue.'),
    'NEEDS_COUNSEL': ('review', 'Deviation that needs counsel', 'The term is outside the acceptable fallback. Counsel reviews the proposed redline.'),
    'ACCEPTABLE_FALLBACK': ('info', 'Acceptable fallback position', 'The term differs from the preferred position but is inside the approved fallback.'),
    'MISSING_CLAUSE': ('review', 'Required clause is missing', 'The playbook requires this clause and no grounded term was found.'),
    'INCONSISTENT_TERM': ('review', 'Term stated inconsistently', 'Two clauses state different values for the same term.'),
    'UNGROUNDED_TERM': ('review', 'Stated term has no verbatim quote', 'The term was dropped from the comparison because its quote is not in the contract.'),
    'INVALID_TERM': ('review', 'Stated term has an unreadable value', 'The term was dropped because its value is not in the expected form.'),
    'PROMPT_INJECTION': ('urgent', 'Contract text contains instructions aimed at the reviewer', 'Treat as suspicious; the rules ignore embedded instructions and a person reviews.'),
    'REDLINE_NOT_FROM_PLAYBOOK': ('urgent', 'Redline text is not the playbook fallback', 'The redline was withheld. Only approved fallback language may be proposed.'),
    'REDLINE_UNKNOWN_CLAUSE': ('review', 'Redline names a clause that does not exist', 'The redline was withheld.'),
    'UNNEEDED_REDLINE': ('info', 'Redline on a topic without a deviation', 'The redline was withheld; the clause meets the playbook.'),
    'MODEL_DISAGREES': ('review', 'Model recommendation differs from the rules', 'The rules decide. The disagreement is logged for review.'),
}


# ---------------------------------------------------------------- playbook contract

def validate_playbook(playbook, contract_type):
    """Strict check of the playbook positions. Returns {topic: position}."""
    obj(playbook, ['id', 'contract_type', 'positions'])
    text(playbook['id'], 'playbook id', 128)
    if playbook['contract_type'] != contract_type:
        raise InputError('playbook.contract_type must match contract.type')
    positions = {}
    for position in rows(playbook['positions'], 'playbook positions', 20, 1):
        obj(position, ['topic', 'preferred', 'fallback', 'rule'])
        topic = position['topic']
        if topic not in TOPICS or topic in positions:
            raise InputError(f'Playbook topics must be unique and one of: {", ".join(TOPICS)}')
        text(position['preferred'], f'{topic} preferred text', 4000)
        text(position['fallback'], f'{topic} fallback text', 4000)
        rule = obj(position['rule'], list(RULE_KEYS[topic]))
        for key, kind in RULE_KEYS[topic].items():
            value = rule[key]
            if not isinstance(value, kind) or (kind is not bool and isinstance(value, bool)):
                raise InputError(f'{topic}.rule.{key} has the wrong type')
            if isinstance(value, NUMBER) and not isinstance(value, bool) and value < 0:
                raise InputError(f'{topic}.rule.{key} must not be negative')
        if topic in ('residuals', 'non_solicit') and rule['if_present'] not in ('counsel', 'walk_away'):
            raise InputError(f'{topic}.rule.if_present must be counsel or walk_away')
        if topic == 'governing_law' and (not rule['allowed'] or any(not isinstance(j, str) or not j.strip() for j in rule['allowed'])):
            raise InputError('governing_law.rule.allowed must list jurisdictions')
        if topic == 'term' and rule['preferred_months'] > rule['max_months']:
            raise InputError('term.rule.preferred_months must not exceed max_months')
        if topic == 'liability_cap' and not rule['walk_away_below'] <= rule['min_multiple'] <= rule['preferred_multiple']:
            raise InputError('liability_cap.rule requires walk_away_below <= min_multiple <= preferred_multiple')
        positions[topic] = position
    missing = [t for t in REQUIRED[contract_type] if t not in positions]
    if missing:
        raise InputError(f'Playbook has no position for required topics: {", ".join(missing)}')
    return positions


def requirement(topic, rule):
    """The playbook position in words, for the deviation table."""
    if topic == 'mutuality':
        return 'mutual obligations' if rule['require_mutual'] else 'mutual or one-way'
    if topic == 'term':
        return f"{rule['preferred_months']} months preferred, at most {rule['max_months']} months"
    if topic == 'exclusions':
        return 'the four standard exclusions only'
    if topic in ('residuals', 'non_solicit'):
        return 'not permitted'
    if topic == 'governing_law':
        return 'one of: ' + ', '.join(rule['allowed'])
    if topic == 'venue':
        return 'courts of the governing-law jurisdiction' if rule['must_match_governing_law'] else 'any'
    if topic == 'auto_renewal':
        return f"no automatic renewal, or a non-renewal notice of at least {rule['min_notice_days']} days"
    if topic == 'liability_cap':
        return (f"{_fmt(rule['preferred_multiple'])}x 12-month fees preferred, at least {_fmt(rule['min_multiple'])}x; "
                f"walk away below {_fmt(rule['walk_away_below'])}x")
    return 'supplier IP indemnity outside the liability cap' if rule['require_uncapped'] else 'any'


def _fmt(number):
    return format(Decimal(str(number)).normalize(), 'f')


# ---------------------------------------------------------------- clause map

NUMBERED = re.compile(r'[ \t]*(?:(?:[Ss]ection|SECTION|[Aa]rticle|ARTICLE|[Cc]lause|CLAUSE)[ \t]+)?(\d{1,2}(?:\.\d{1,2})*)\.?(?:[ \t]*[-–—:])?[ \t]+(?=["“(\[A-Z])')
LETTERED = re.compile(r'[ \t]*\(([a-z])\)[ \t]+')


def clauses(contract_text):
    """Split the text into clauses: [{'ref', 'start', 'end', 'text'}] in document order.

    A clause starts on a line that begins with a number (1, 2.3, Section 4, ARTICLE 5) or a
    bracketed letter ((a), (b)); a lettered clause takes the number of the clause above it.
    Text before the first numbered line is the preamble. Refs are unique."""
    starts, parent, offset = [], None, 0
    for line in contract_text.splitlines(keepends=True):
        numbered = NUMBERED.match(line)
        if numbered:
            parent = numbered.group(1)
            starts.append((offset, parent))
        else:
            lettered = LETTERED.match(line)
            if lettered and parent:
                starts.append((offset, f'{parent}({lettered.group(1)})'))
        offset += len(line)
    if not starts or starts[0][0] > 0:
        starts.insert(0, (0, 'preamble'))
    spans, seen = [], {}
    for i, (start, ref) in enumerate(starts):
        end = starts[i+1][0] if i+1 < len(starts) else len(contract_text)
        seen[ref] = seen.get(ref, 0) + 1
        unique_ref = ref if seen[ref] == 1 else f'{ref}#{seen[ref]}'
        spans.append({'ref': unique_ref, 'start': start, 'end': end, 'text': contract_text[start:end].strip()})
    return spans


def normalize_ref(ref):
    """'Section 3(a).' -> '3(a)'; 'clause 2.1' -> '2.1'."""
    value = re.sub(r'^(?:section|article|clause|§)\s*', '', str(ref or '').strip().lower())
    return re.sub(r'\s+', '', value).rstrip('.')


def clause_at(spans, offset):
    for span in spans:
        if span['start'] <= offset < span['end']:
            return span['ref']
    return spans[-1]['ref']


# ---------------------------------------------------------------- terms

def jurisdiction(name):
    value = re.sub(r'[^a-z ]', ' ', str(name).lower())
    value = re.sub(r'\b(the|laws?|of|state|commonwealth|courts?|county|federal)\b', ' ', value)
    value = ' '.join(value.split())
    return JURISDICTION_ALIASES.get(value, value)


def parse_value(topic, value):
    """Normalize a stated value. Raises InputError when it is not in the form VALUE_FORMS gives."""
    raw = str(value).strip().lower()
    simple = {'mutuality': ('mutual', 'one_way'), 'exclusions': ('standard', 'overbroad'), 'residuals': ('present',),
              'non_solicit': ('present',), 'ip_indemnity': ('uncapped', 'capped')}
    if topic in simple:
        if raw not in simple[topic]:
            raise InputError(f'{topic} must be one of {", ".join(simple[topic])}')
        return raw
    if topic == 'term':
        if raw == 'perpetual':
            return raw
        if re.fullmatch(r'\d{1,3}', raw) and 0 < int(raw) <= 600:
            return int(raw)
        raise InputError('term must be months as digits or perpetual')
    if topic in ('governing_law', 'venue'):
        place = jurisdiction(raw)
        if not place or len(place) > 60:
            raise InputError(f'{topic} must name a jurisdiction')
        return place
    if topic == 'auto_renewal':
        if raw in ('none', 'no_notice'):
            return raw
        if re.fullmatch(r'\d{1,3}', raw):
            return int(raw)
        raise InputError('auto_renewal must be none, no_notice or notice days as digits')
    if topic == 'liability_cap':
        if raw == 'uncapped':
            return raw
        try:
            multiple = Decimal(raw)
        except InvalidOperation as exc:
            raise InputError('liability_cap must be a decimal multiple or uncapped') from exc
        if not multiple.is_finite() or not Decimal('0') < multiple <= Decimal('100'):
            raise InputError('liability_cap must be between 0 and 100')
        return multiple
    raise InputError(f'Unknown topic {topic}')


def shown(topic, value):
    if topic == 'term' and isinstance(value, int):
        return f'{value} months'
    if topic == 'auto_renewal' and isinstance(value, int):
        return f'{value} days notice'
    if topic == 'liability_cap' and isinstance(value, Decimal):
        return f'{_fmt(value)}x'
    if topic in ('governing_law', 'venue'):
        return value.title().replace(' And ', ' and ')
    return str(value)


def ground_terms(terms, contract_text, spans):
    """Check every stated term. A term is grounded when its quote (at least MIN_QUOTE characters)
    exists verbatim in the contract; its clause is where the quote is. Returns (rows, codes)."""
    out, codes = [], []
    for term in terms:
        topic, quote = term.get('topic'), str(term.get('quote', ''))
        row = {'topic': topic, 'value': str(term.get('value', '')), 'quote': quote, 'clause_ref': None, 'grounded': False}
        position = contract_text.find(quote) if len(quote.strip()) >= MIN_QUOTE else -1
        if topic not in TOPICS or position < 0:
            codes.append('UNGROUNDED_TERM')
            out.append(row)
            continue
        row['clause_ref'] = clause_at(spans, position)
        try:
            row['parsed'] = parse_value(topic, row['value'])
        except InputError:
            codes.append('INVALID_TERM')
            out.append(row)
            continue
        row['grounded'] = True
        out.append(row)
    return out, codes


# ---------------------------------------------------------------- comparison and route

def _severity(topic, value, rule, law):
    """Risk tier of one grounded value: None (meets preferred), acceptable, counsel or walk_away."""
    if topic == 'mutuality':
        return 'counsel' if value == 'one_way' and rule['require_mutual'] else None
    if topic == 'term':
        if value == 'perpetual' or value > rule['max_months']:
            return 'counsel'
        return 'acceptable' if value > rule['preferred_months'] else None
    if topic == 'exclusions':
        return 'counsel' if value == 'overbroad' else None
    if topic in ('residuals', 'non_solicit'):
        return rule['if_present']
    if topic == 'governing_law':
        return None if value in {jurisdiction(j) for j in rule['allowed']} else 'counsel'
    if topic == 'venue':
        return 'counsel' if rule['must_match_governing_law'] and law is not None and value != law else None
    if topic == 'auto_renewal':
        if value == 'none':
            return None
        return 'counsel' if value == 'no_notice' or value < rule['min_notice_days'] else None
    if topic == 'liability_cap':
        if value == 'uncapped':
            return None
        if value < Decimal(str(rule['walk_away_below'])):
            return 'walk_away'
        if value < Decimal(str(rule['min_multiple'])):
            return 'counsel'
        return 'acceptable' if value < Decimal(str(rule['preferred_multiple'])) else None
    return 'counsel' if value == 'capped' and rule['require_uncapped'] else None


def compare(contract_type, positions, grounded):
    """Deviations from the playbook: [{topic, found, playbook, severity, clause_ref, kind}] in topic order."""
    by_topic = {}
    for row in grounded:
        if row['grounded']:
            by_topic.setdefault(row['topic'], []).append(row)
    laws = {r['parsed'] for r in by_topic.get('governing_law', [])}
    law = next(iter(laws)) if len(laws) == 1 else None
    deviations = []
    for topic in TOPICS:
        position = positions.get(topic)
        if position is None:
            continue
        need = requirement(topic, position['rule'])
        items = by_topic.get(topic, [])
        if not items:
            if topic in REQUIRED[contract_type]:
                deviations.append({'topic': topic, 'found': 'missing', 'playbook': need, 'severity': 'counsel', 'clause_ref': None, 'kind': 'missing'})
            continue
        values = list(dict.fromkeys(r['parsed'] for r in items))
        refs = list(dict.fromkeys(r['clause_ref'] for r in items))
        if len(values) > 1:
            deviations.append({'topic': topic, 'found': ' / '.join(shown(topic, v) for v in values), 'playbook': need,
                               'severity': 'counsel', 'clause_ref': ', '.join(refs), 'kind': 'inconsistent'})
            continue
        severity = _severity(topic, values[0], position['rule'], law)
        if severity:
            found = shown(topic, values[0]) + (f' (governing law {shown("governing_law", law)})' if topic == 'venue' else '')
            deviations.append({'topic': topic, 'found': found, 'playbook': need, 'severity': severity,
                               'clause_ref': refs[0], 'kind': 'threshold'})
    return deviations


def route_for(deviations, codes):
    severities = {d['severity'] for d in deviations}
    if 'walk_away' in severities:
        return 'walk_away'
    if 'counsel' in severities or set(codes) & set(ESCALATING):
        return 'counsel_review'
    return 'approve_standard'


def assess(contract, positions, terms, flags=()):
    """Ground, compare and route. Shared by the compare_to_playbook tool, the agent and the baseline."""
    spans = clauses(contract['text'])
    grounded, codes = ground_terms(terms, contract['text'], spans)
    codes = [f for f in flags if f in MODEL_FLAGS] + codes
    deviations = compare(contract['type'], positions, grounded)
    return {'terms': grounded, 'deviations': deviations, 'codes': list(dict.fromkeys(codes)), 'route': route_for(deviations, codes)}


def normalize_text(value):
    return ' '.join(str(value).split())


def check_redlines(proposals, positions, deviations, spans):
    """Accept a redline only when it is the playbook fallback, word for word, for a topic with a
    counsel or walk-away deviation, on an existing clause (or empty clause_ref to insert a missing one)."""
    refs = {s['ref'] for s in spans}
    needed = {d['topic'] for d in deviations if d['severity'] in ('counsel', 'walk_away')}
    redlines, codes = [], []
    for item in proposals:
        topic, ref, replacement = item.get('topic'), normalize_ref(item.get('clause_ref')), str(item.get('replacement_text', ''))
        position = positions.get(topic)
        code = None
        if position is None or normalize_text(replacement) != normalize_text(position['fallback']):
            code = 'REDLINE_NOT_FROM_PLAYBOOK'
        elif ref and ref not in refs:
            code = 'REDLINE_UNKNOWN_CLAUSE'
        elif topic not in needed:
            code = 'UNNEEDED_REDLINE'
        if code:
            codes.append(code)
        redlines.append({'topic': topic, 'clause_ref': ref or None, 'replacement_text': replacement,
                         'source': None if code == 'REDLINE_NOT_FROM_PLAYBOOK' else 'playbook_fallback',
                         'status': 'withheld' if code else 'draft', 'problem': code})
    return redlines, list(dict.fromkeys(codes))


# ---------------------------------------------------------------- output

def review(contract, positions, requester, terms, flags, proposals, evidence, model_route=None):
    """Full decision and shared output shape for the agent and the baseline."""
    result = assess(contract, positions, terms, flags)
    redlines, redline_codes = check_redlines(proposals, positions, result['deviations'], clauses(contract['text']))
    route = result['route']
    codes = []
    for deviation in result['deviations']:
        codes.append({'missing': 'MISSING_CLAUSE', 'inconsistent': 'INCONSISTENT_TERM'}.get(deviation['kind'])
                     or {'walk_away': 'WALK_AWAY_TERM', 'counsel': 'NEEDS_COUNSEL', 'acceptable': 'ACCEPTABLE_FALLBACK'}[deviation['severity']])
    codes += result['codes'] + redline_codes
    if model_route is not None and model_route != route:
        codes.append('MODEL_DISAGREES')
    findings = []
    for code in dict.fromkeys(codes):
        severity, title, detail = FINDING_TEXT[code]
        topics = [d['topic'] for d in result['deviations'] if (d['kind'] == 'missing' and code == 'MISSING_CLAUSE')
                  or (d['kind'] == 'inconsistent' and code == 'INCONSISTENT_TERM')
                  or (d['kind'] == 'threshold' and code == {'walk_away': 'WALK_AWAY_TERM', 'counsel': 'NEEDS_COUNSEL', 'acceptable': 'ACCEPTABLE_FALLBACK'}[d['severity']])]
        findings.append({'code': code, 'severity': severity, 'title': title, 'detail': detail + (f" Topics: {', '.join(topics)}." if topics else ''),
                         'evidence_ids': [contract['id']]})
    drafts = [r for r in redlines if r['status'] == 'draft']
    actions = []
    if route == 'approve_standard':
        actions.append({'action': 'approve_standard', 'owner': 'legal ops', 'status': 'awaiting_approval', 'contract_id': contract['id'],
                        'note': 'Every checked term meets the playbook. Signature still needs the legal ops approver.'})
    else:
        actions.append({'action': 'counsel_review' if route == 'counsel_review' else 'walk_away_review', 'owner': 'commercial counsel',
                        'status': 'queued', 'contract_id': contract['id'], 'topics': [d['topic'] for d in result['deviations'] if d['severity'] != 'acceptable'],
                        'reasons': list(dict.fromkeys(codes))})
        if drafts:
            actions.append({'action': 'send_redline', 'owner': 'commercial counsel', 'status': 'draft', 'redlines': drafts})
    actions.append({'action': 'notify_requester', 'owner': requester['role'], 'status': 'draft', 'route': route})
    serious = [d['topic'] for d in result['deviations'] if d['severity'] != 'acceptable']
    summary = {'approve_standard': f"{contract['type']} with {contract['counterparty']} meets the playbook. Ready for legal ops approval.",
               'counsel_review': f"{contract['type']} with {contract['counterparty']} needs counsel: {', '.join(serious + [c for c in result['codes']]) or 'review'}.",
               'walk_away': f"{contract['type']} with {contract['counterparty']} has a walk-away term: "
                            f"{', '.join(d['topic'] for d in result['deviations'] if d['severity'] == 'walk_away')}. Counsel decides."}[route]
    terms_out = [{k: r[k] for k in ('topic', 'value', 'quote', 'clause_ref', 'grounded')} for r in result['terms']]
    deviations = [{k: d[k] for k in ('topic', 'found', 'playbook', 'severity', 'clause_ref')} for d in result['deviations']]
    return {'project': 'contract-review-agent', 'summary': summary,
            'metrics': {'route': route, 'deviations': len(deviations), 'walk_away': sum(d['severity'] == 'walk_away' for d in deviations),
                        'counsel': sum(d['severity'] == 'counsel' for d in deviations), 'terms': len(terms_out),
                        'ungrounded_terms': sum(not t['grounded'] for t in terms_out),
                        'redlines_released': len(drafts), 'redlines_withheld': len(redlines) - len(drafts)},
            'findings': findings, 'actions': actions, 'human_review_required': True,
            'contract': {k: contract[k] for k in ('id', 'counterparty', 'type', 'paper')}, 'requester': dict(requester),
            'route': route, 'terms': terms_out, 'deviations': deviations, 'redlines': redlines, 'evidence': list(evidence)}
