"""Deterministic support policy rules: visibility, applicable version, eligibility, route.

The model reads the ticket, classifies the intent, finds the order and drafts the reply.
This module decides. It filters policy sections by tenant, role and effective date before
the model can see them, picks the policy version in force when the order was placed,
computes eligibility from the order state and the policy parameters, applies the refund
limit for the requester's role, and verifies that every cited quote exists verbatim in a
section the requester may see. The agent and the baseline call the same functions.
"""
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from enterprise_ai.common import InputError

ROLES = ('customer', 'agent', 'manager')
INTENTS = ('cancel', 'return', 'refund', 'replace', 'status', 'other')
ACTIONS = ('refund', 'cancel', 'return', 'replace', 'escalate', 'no_action')
ROUTES = ('resolve', 'escalate', 'refuse')
ORDER_STATUSES = ('pending', 'shipped', 'delivered', 'cancelled')
MODEL_FLAGS = ('PROMPT_INJECTION', 'SUSPICIOUS_REQUEST')
MONEY_ACTIONS = ('refund', 'cancel', 'return', 'replace')
ESCALATING_FINDINGS = ('PROMPT_INJECTION', 'SUSPICIOUS_REQUEST', 'IDENTITY_MISMATCH', 'CROSS_TENANT_ORDER', 'PERMISSION_LEAK')
SEARCH_LIMIT = 5
STOPWORDS = {'a', 'an', 'the', 'of', 'to', 'for', 'and', 'or', 'in', 'on', 'is', 'are', 'be', 'my', 'i', 'it', 'this', 'that',
             'with', 'can', 'do', 'does', 'what', 'about', 'policy', 'order', 'please', 'we', 'you', 'your', 'our', 'customer'}

FINDING_TEXT = {
    'IDENTITY_MISMATCH': ('urgent', 'Order belongs to a different customer', 'The order exists but is not on this customer account. Nothing about it was disclosed. Verify identity before any action.'),
    'CROSS_TENANT_ORDER': ('urgent', 'Order belongs to another tenant', 'The order number is not in this tenant. Nothing about it was disclosed.'),
    'ORDER_NOT_FOUND': ('review', 'Order not found', 'No order with this number exists for the customer. Ask for the correct order number.'),
    'ORDER_NOT_IDENTIFIED': ('review', 'No order identified', 'The request needs an order but none could be identified from the ticket.'),
    'AMBIGUOUS_INTENT': ('review', 'Intent is ambiguous', 'The ticket asks for incompatible or unclear actions. A person decides.'),
    'CANCEL_AFTER_SHIPMENT': ('info', 'Cancellation requested after shipment', 'Policy allows cancellation only before the order ships.'),
    'NOT_DELIVERED': ('info', 'Order not yet delivered', 'Returns, refunds and replacements apply to delivered orders.'),
    'ORDER_CANCELLED': ('info', 'Order already cancelled', 'No further action is possible on a cancelled order.'),
    'OUTSIDE_RETURN_WINDOW': ('info', 'Outside the return window', 'The policy window measured from delivery has passed.'),
    'GOODWILL_EXCEPTION': ('review', 'Manager goodwill exception applied', 'The return is outside the window but inside the manager goodwill allowance.'),
    'OVER_LIMIT': ('review', 'Amount above the requester limit', 'The amount exceeds the refund limit for this role and needs a higher approver.'),
    'ALREADY_REFUNDED': ('info', 'Nothing left to refund', 'The refunded balance already covers the order.'),
    'UNKNOWN_SKU': ('review', 'Item not on the order', 'The proposal names an item that is not on this order; the whole refundable balance was used instead.'),
    'PROMPT_INJECTION': ('urgent', 'Ticket contains instructions aimed at the system', 'Treat as suspicious; the rules ignore embedded instructions.'),
    'SUSPICIOUS_REQUEST': ('urgent', 'Ticket shows pressure or an unusual request', 'A person reviews before any action.'),
    'PERMISSION_LEAK': ('urgent', 'Reply quoted a section the requester may not see', 'The citation was removed and the reply withheld. Review the model output.'),
    'CITATION_NOT_VERBATIM': ('review', 'Citation is not an exact quote', 'The quote does not exist in the named section. It was removed from the reply.'),
    'UNGROUNDED_POLICY_CLAIM': ('review', 'Reply states a policy fact without a citation', 'Every policy statement in a reply must cite a visible section.'),
    'REPLY_CONTRADICTS_DECISION': ('urgent', 'Reply promises an action the rules did not allow', 'The reply was withheld. A person rewrites it.'),
    'MODEL_DISAGREES': ('review', 'Model proposal differs from the rules', 'The rules decide. The disagreement is logged for review.'),
}


def money(value):
    try:
        return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except Exception as exc:  # noqa: BLE001
        raise InputError(f'Invalid amount {value!r}') from exc


def parse_day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise InputError(f'Invalid date {value!r}') from exc


# ---------------------------------------------------------------- policies

def policy_versions(policies, tenant_id):
    versions = [p for p in policies if p['tenant_id'] == tenant_id]
    return sorted(versions, key=lambda p: (parse_day(p['effective_from']), str(p['version'])))


def applicable_policy(policies, tenant_id, on):
    """The version in force on `on`: the latest effective_from that is not after `on`."""
    chosen = None
    for policy in policy_versions(policies, tenant_id):
        if parse_day(policy['effective_from']) <= on:
            chosen = policy
    return chosen


def superseded_on(policies, policy):
    later = [parse_day(p['effective_from']) for p in policy_versions(policies, policy['tenant_id'])
             if parse_day(p['effective_from']) > parse_day(policy['effective_from'])]
    return min(later).isoformat() if later else None


def section_rows(policies):
    """Flatten every section with its policy metadata. Section ids must be unique."""
    rows, seen = [], set()
    for policy in policies:
        for section in policy['sections']:
            if section['section_id'] in seen:
                raise InputError(f"Duplicate section id {section['section_id']}")
            seen.add(section['section_id'])
            rows.append({'policy_id': policy['policy_id'], 'tenant_id': policy['tenant_id'], 'version': policy['version'],
                         'effective_from': policy['effective_from'], 'superseded_on': superseded_on(policies, policy),
                         'visibility': list(section.get('visibility', policy.get('visibility', []))),
                         'section_id': section['section_id'], 'title': section['title'], 'text': section['text'],
                         'topic': section.get('topic', '')})
    return rows


def visible_sections(policies, tenant_id, role, as_of):
    """Permission filter. Runs before retrieval: other tenants, roles without access and
    versions not yet effective on `as_of` never reach the ranking step."""
    return [s for s in section_rows(policies)
            if s['tenant_id'] == tenant_id and role in s['visibility'] and parse_day(s['effective_from']) <= as_of]


def hidden_sections(policies, tenant_id, role, as_of):
    allowed = {s['section_id'] for s in visible_sections(policies, tenant_id, role, as_of)}
    return [s for s in section_rows(policies) if s['section_id'] not in allowed]


def tokens(text):
    words = re.findall(r'[a-z0-9]+', str(text).lower())
    return {w[:-1] if len(w) > 4 and w.endswith('s') else w for w in words if w not in STOPWORDS}


def search(sections, query, limit=SEARCH_LIMIT):
    """Rank already-filtered sections by token overlap with the query. Title hits count double."""
    query_tokens = tokens(query)
    scored = []
    for section in sections:
        body, title = tokens(section['text']), tokens(section['title'])
        score = len(query_tokens & body) + 2*len(query_tokens & title)
        scored.append((score, section))
    scored.sort(key=lambda pair: (-pair[0], pair[1]['effective_from'], pair[1]['section_id']))
    if not query_tokens or all(score == 0 for score, _ in scored):
        return [s for _, s in scored[:limit]]
    return [s for score, s in scored if score > 0][:limit]


def section_for_topic(policy, topic):
    for section in policy.get('sections', []):
        if section.get('topic') == topic:
            return section
    return None


# ---------------------------------------------------------------- orders

def find_order(systems, order_id, customer_id, tenant_id):
    """Returns (order, reason). reason: ok | not_found | other_customer | other_tenant | no_order_id.
    The caller never learns anything about an order it may not see."""
    wanted = str(order_id or '').strip().upper()
    if not wanted:
        return None, 'no_order_id'
    for order in systems['orders']:
        if str(order['id']).upper() == wanted:
            if order['tenant_id'] != tenant_id:
                return None, 'other_tenant'
            if order['customer_id'] != customer_id:
                return None, 'other_customer'
            return order, 'ok'
    return None, 'not_found'


def refundable_balance(order):
    return max(Decimal('0.00'), money(order['total']) - money(order.get('refunded', 0)))


def days_since_delivery(order, as_of):
    if order.get('status') != 'delivered' or not order.get('delivered_on'):
        return None
    return (as_of - parse_day(order['delivered_on'])).days


def order_view(order, policies, as_of):
    """The order as the model sees it: the record plus facts computed by code."""
    policy = applicable_policy(policies, order['tenant_id'], parse_day(order['placed_on']))
    view = dict(order)
    view['refundable_balance'] = float(refundable_balance(order))
    view['days_since_delivery'] = days_since_delivery(order, as_of)
    view['applicable_policy'] = {'policy_id': policy['policy_id'], 'version': policy['version'],
                                 'effective_from': policy['effective_from']} if policy else None
    return view


def line_amount(order, skus):
    """Sum of the named lines (qty x unit price). Returns (amount, unknown_skus)."""
    wanted = [str(s).strip().upper() for s in skus if str(s).strip()]
    by_sku = {str(l['sku']).upper(): l for l in order['lines']}
    unknown = [s for s in wanted if s not in by_sku]
    total = sum((money(by_sku[s]['qty'])*money(by_sku[s]['unit_price']) for s in wanted if s in by_sku), Decimal('0'))
    return money(total), unknown


def role_limit(limits, role):
    return money(limits['manager_refund_limit'] if role == 'manager' else limits['agent_refund_limit'])


# ---------------------------------------------------------------- decision

def decide(intent, order_id, order, reason, policies, tenant_id, role, limits, as_of, skus=(), flags=()):
    """Compute the final action and route. Returns a decision dict.

    intent: model or baseline classification. order/reason: from find_order.
    skus: items the request concerns (empty = whole order). flags: model-only flags.
    """
    if intent not in INTENTS or role not in ROLES:
        raise InputError('Unsupported intent or role')
    findings, refs = [], []
    for flag in flags:
        if flag in MODEL_FLAGS and flag not in findings:
            findings.append(flag)
    on = parse_day(order['placed_on']) if order else as_of
    policy = applicable_policy(policies, tenant_id, on)
    params = (policy or {}).get('parameters', {})
    amount, action_skus, days, window = None, [], None, None

    def ref(topic):
        section = section_for_topic(policy, topic) if policy else None
        if section and section['section_id'] not in refs:
            refs.append(section['section_id'])

    if intent == 'other':
        route, action = 'escalate', 'escalate'
        findings.append('AMBIGUOUS_INTENT')
    elif reason == 'other_customer':
        route, action = 'refuse', 'no_action'
        findings.append('IDENTITY_MISMATCH')
    elif reason == 'other_tenant':
        route, action = 'refuse', 'no_action'
        findings.append('CROSS_TENANT_ORDER')
    elif reason == 'not_found':
        route, action = 'refuse', 'no_action'
        findings.append('ORDER_NOT_FOUND')
    elif reason == 'no_order_id':
        route, action = 'escalate', 'escalate'
        findings.append('ORDER_NOT_IDENTIFIED')
    elif intent == 'status':
        route, action = 'resolve', 'no_action'
        ref('shipping')
    else:
        status = order['status']
        window = int(params.get('return_window_days', 0))
        if intent == 'replace':
            window = int(params.get('replacement_window_days', window))
        goodwill = int(params.get('manager_goodwill_days', 0)) if role == 'manager' else 0
        days = days_since_delivery(order, as_of)
        balance = refundable_balance(order)
        if intent == 'cancel':
            ref('cancellations')
            if status == 'pending':
                route, action, amount = 'resolve', 'cancel', balance
            elif status == 'cancelled':
                route, action = 'refuse', 'no_action'
                findings.append('ORDER_CANCELLED')
            else:
                route, action = 'refuse', 'no_action'
                findings.append('CANCEL_AFTER_SHIPMENT')
        elif intent in ('return', 'refund', 'replace'):
            ref({'return': 'returns', 'refund': 'damaged', 'replace': 'replacements'}[intent])
            if status == 'cancelled':
                route, action = 'refuse', 'no_action'
                findings.append('ORDER_CANCELLED')
            elif status != 'delivered':
                route, action = 'refuse', 'no_action'
                findings.append('NOT_DELIVERED')
            elif days > window and not (intent != 'replace' and days <= window + goodwill):
                route, action = 'refuse', 'no_action'
                findings.append('OUTSIDE_RETURN_WINDOW')
            else:
                if days > window:
                    findings.append('GOODWILL_EXCEPTION')
                    ref('goodwill')
                if intent == 'replace':
                    route, action = 'resolve', 'replace'
                    action_skus = [str(s).upper() for s in skus if str(s).strip()]
                else:
                    requested, unknown = line_amount(order, skus)
                    if unknown:
                        findings.append('UNKNOWN_SKU')
                    if skus and not unknown and requested > 0:
                        amount, action_skus = min(requested, balance), [str(s).upper() for s in skus]
                    else:
                        amount = balance
                    if amount <= 0:
                        route, action, amount = 'refuse', 'no_action', None
                        findings.append('ALREADY_REFUNDED')
                    else:
                        route, action = 'resolve', intent
        else:  # pragma: no cover - INTENTS is closed
            raise InputError('Unsupported intent')
    if route == 'resolve' and amount is not None and action in ('refund', 'return') and amount > role_limit(limits, role):
        route, action = 'escalate', 'escalate'
        findings.append('OVER_LIMIT')
        ref('refund_limits')
    if route == 'resolve' and any(f in findings for f in MODEL_FLAGS):
        route, action = 'escalate', 'escalate'
    needs_escalation = route == 'escalate' or any(f in findings for f in ESCALATING_FINDINGS)
    return {'route': route,
            'action': {'type': action, 'order_id': order['id'] if order else (str(order_id or '').strip().upper() or None),
                       'amount': float(amount) if amount is not None else None, 'skus': action_skus,
                       'reason': ', '.join(findings) or f'{intent} eligible under policy'},
            'needs_escalation': needs_escalation, 'findings': findings, 'policy_refs': refs,
            'policy': {'policy_id': policy['policy_id'], 'version': policy['version']} if policy else None,
            'days_since_delivery': days, 'window_days': window, 'lookup': reason}


# ---------------------------------------------------------------- grounding and leaks

def _in_visible(quote, visible):
    return any(quote in s['text'] for s in visible)


def check_citations(cited, visible, hidden):
    """Split citations into verbatim-visible, leaks (hidden section or hidden-only text) and fabrications."""
    visible_by_id = {s['section_id']: s for s in visible}
    hidden_by_id = {s['section_id']: s for s in hidden}
    valid, codes = [], []
    for item in cited:
        sid, quote = str(item.get('section_id', '')), str(item.get('quote', ''))
        if sid in visible_by_id and quote.strip() and quote in visible_by_id[sid]['text']:
            valid.append({'policy_id': visible_by_id[sid]['policy_id'], 'section_id': sid, 'quote': quote})
        elif sid in hidden_by_id or (len(quote.strip()) >= 20 and not _in_visible(quote, visible)
                                     and any(quote in s['text'] for s in hidden)):
            codes.append('PERMISSION_LEAK')
        else:
            codes.append('CITATION_NOT_VERBATIM')
    return valid, sorted(set(codes))


def sentences(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', str(text or '')) if s.strip()]


def leaked_phrases(reply, hidden, visible=()):
    """Sentences of hidden sections that appear verbatim in the reply and in no visible section."""
    found = []
    for section in hidden:
        for sentence in sentences(section['text']):
            if len(sentence) >= 40 and sentence in reply and not _in_visible(sentence, visible):
                found.append(section['section_id'])
                break
    return found


POLICY_FACT = re.compile(r'\b(\d+\s*(?:business\s+|calendar\s+)?days?|policy|eligible|window|cannot be cancelled|'
                         r'can(?:not|\'t) be returned|restocking|before (?:it|the order) ships?|once (?:an order|it) has shipped)\b', re.I)
PROMISE = re.compile(r'\b(refund|replacement|cancellation|return)\b[^.]{0,60}\b(has been|have been|is being|was|were|is now|'
                     r'already)\s+(issued|processed|arranged|approved|completed|sent|confirmed|cancelled)', re.I)
PROMISE_ALT = re.compile(r"\b(I|we)(?:'ve| have)\s+(issued|processed|refunded|cancelled|approved|arranged)\b", re.I)
NEGATION = re.compile(r"\b(no|not|never|without|hasn't|haven't|isn't|wasn't|weren't|won't|cannot|can't)\b", re.I)


def promised_completion(reply):
    """True when a sentence states that an action is already done, and the sentence does not negate it.
    "No refund has been issued" and "the refund has not been processed" are correct statements, not promises."""
    for sentence in sentences(reply):
        match = PROMISE.search(sentence) or PROMISE_ALT.search(sentence)
        if match and not NEGATION.search(sentence[:match.end()]):
            return True
    return False


def reply_checks(reply, decision, valid_citations, hidden, visible=()):
    """Code checks on the drafted reply. Returns (codes, status)."""
    codes = []
    if leaked_phrases(reply, hidden, visible):
        codes.append('PERMISSION_LEAK')
    facts = [s for s in sentences(reply) if POLICY_FACT.search(s)]
    if facts and not valid_citations:
        codes.append('UNGROUNDED_POLICY_CLAIM')
    if decision['route'] != 'resolve' and promised_completion(reply):
        codes.append('REPLY_CONTRADICTS_DECISION')
    status = 'withheld' if {'PERMISSION_LEAK', 'REPLY_CONTRADICTS_DECISION'} & set(codes) else 'draft'
    return codes, status


# ---------------------------------------------------------------- output

def build_output(ticket, requester, intent, decision, cited, reply, reply_status, evidence, extra_findings=(), model_proposal=None, currency='USD'):
    """Shared output shape for the agent and the baseline."""
    codes = list(decision['findings'])
    for code in extra_findings:
        if code not in codes:
            codes.append(code)
    route = decision['route']
    if 'PERMISSION_LEAK' in codes and route == 'resolve':
        route = 'escalate'
    needs_escalation = decision['needs_escalation'] or route == 'escalate' or 'PERMISSION_LEAK' in codes
    findings = []
    for code in codes:
        severity, title, detail = FINDING_TEXT[code]
        findings.append({'code': code, 'severity': severity, 'title': title, 'detail': detail,
                         'evidence_ids': [ticket['id']] + list(decision['policy_refs'])})
    action = decision['action']
    actions = []
    if route == 'resolve' and action['type'] in MONEY_ACTIONS:
        actions.append({'action': action['type'], 'owner': 'support manager' if requester['role'] == 'manager' else 'support agent',
                        'status': 'awaiting_approval', 'order_id': action['order_id'], 'amount': action['amount'],
                        'currency': currency, 'skus': action['skus'], 'policy_refs': decision['policy_refs']})
    elif route == 'escalate':
        owner = 'finance approver' if 'OVER_LIMIT' in codes else 'support manager'
        actions.append({'action': 'escalate', 'owner': owner, 'status': 'queued', 'order_id': action['order_id'],
                        'amount': action['amount'], 'reasons': codes})
    actions.append({'action': 'send_reply', 'owner': 'support agent', 'status': reply_status, 'channel': ticket['channel'], 'text': reply})
    summary = {'resolve': f"{intent.capitalize()} request is eligible: propose {action['type']} on {action['order_id']}" +
                          (f" for {currency} {action['amount']:.2f}" if action['amount'] else '') + '. Awaiting approval.',
               'escalate': f"Escalate: {', '.join(codes) or 'review needed'}.",
               'refuse': f"Request is not eligible: {', '.join(codes) or 'policy'}. Reply drafted."}[route]
    if reply_status == 'withheld':
        summary += ' Reply withheld pending review.'
    return {'project': 'support-resolution-agent', 'summary': summary,
            'metrics': {'route': route, 'action': action['type'], 'amount': action['amount'], 'intent': intent,
                        'order_id': action['order_id'], 'policy_version': (decision['policy'] or {}).get('version'),
                        'citations': len(cited), 'reply_status': reply_status},
            'findings': findings, 'actions': actions,
            'intent': intent, 'order_id': action['order_id'], 'applicable_policy': decision['policy'],
            'decision': {'route': route, 'action': action, 'needs_escalation': needs_escalation,
                         'days_since_delivery': decision['days_since_delivery'], 'window_days': decision['window_days'],
                         'lookup': decision['lookup'], 'policy_refs': decision['policy_refs']},
            'needs_escalation': needs_escalation, 'cited_policy': cited, 'draft_reply': reply, 'evidence': list(evidence),
            'model_proposal': model_proposal}
