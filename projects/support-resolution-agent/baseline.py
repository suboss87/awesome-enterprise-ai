"""Rules-only baseline in the style of a keyword help-desk macro.

A keyword classifier picks the intent, a regex finds the first order number, a word
match on the order lines guesses the affected item, and a short blocklist looks for
instructions aimed at the system. The decision then goes through the same `policy.py`
rules as the agent, and the reply is a template that quotes the first sentence of the
section the rules relied on. The comparison therefore isolates the reading step.
"""
import importlib.util
import re
from pathlib import Path

_here = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('support_policy_b', _here/'policy.py')
policy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(policy)
_aspec = importlib.util.spec_from_file_location('support_agent_b', _here/'agent.py')
agent_module = importlib.util.module_from_spec(_aspec)
_aspec.loader.exec_module(agent_module)

INTENT_PATTERNS = [
    ('cancel', r"\bcancel|\bstop\b.{0,20}\border|does not ship|doesn't ship|not ship\b"),
    ('replace', r"\breplace|\bexchange|\bswap\b"),
    ('refund', r"\brefund|money back|reimburs"),
    ('return', r"\breturn|send (?:it |them |everything |back |the whole order )*back|take (?:it |them )?back"),
    ('status', r"where is|\btrack|\bstatus\b|when will .{0,40}arrive|hasn't arrived|not arrived|has it shipped"),
]
INJECTION = re.compile(r"ignore (?:the |all |your |previous |prior )*(?:return )?(?:policy|instructions|rules)|system override|"
                       r"skip (?:the |all )?(?:eligibility )?checks|without consulting", re.I)
ORDER_ID = re.compile(r'\bORD-[A-Z]-\d+\b', re.I)


def classify(text):
    for intent, pattern in INTENT_PATTERNS:
        if re.search(pattern, text, re.I):
            return intent
    return 'other'


def affected_skus(text, order):
    """Lines whose description appears in the ticket. Empty means the whole order."""
    if order is None:
        return []
    lowered = text.lower()
    hits = [l['sku'] for l in order['lines'] if l['description'].lower() in lowered]
    return hits if 0 < len(hits) < len(order['lines']) or (hits and len(order['lines']) == 1 and 'item' in lowered) else []


def template_reply(brand, name, decision, order, currency):
    action = decision['action']
    oid = action['order_id'] or 'your order'
    amount = f"{currency} {action['amount']:.2f}" if action['amount'] else ''
    codes = set(decision['findings'])
    if decision['route'] == 'resolve':
        body = {'cancel': f'We have requested the cancellation of {oid}. Once approved, you will receive a confirmation and a refund of {amount}.',
                'return': f'We have requested a return for {oid}. Once approved, we will send return instructions and refund {amount} after the items arrive.',
                'refund': f'We have requested a refund of {amount} for the affected item on {oid}. Once approved, it will be returned to your original payment method.',
                'replace': f'We have requested a replacement for the affected item on {oid}. Once approved, we will confirm the dispatch date.',
                'no_action': (f"{oid} is currently {order['status']}" + (f", shipped on {order['shipped_on']}" if order and order.get('shipped_on') else '') + '.') if order else 'We have checked your order.'}[action['type']]
    elif decision['route'] == 'escalate':
        body = f'We have passed your request about {oid} to a specialist who will get back to you shortly.'
    elif 'OUTSIDE_RETURN_WINDOW' in codes:
        body = f"{oid} was delivered {decision['days_since_delivery']} days ago, which is outside the {decision['window_days']}-day window, so we are unable to accept a return or refund."
    elif 'CANCEL_AFTER_SHIPMENT' in codes:
        body = f'{oid} has already shipped, so it can no longer be cancelled. You can return it after delivery under the returns policy.'
    elif 'NOT_DELIVERED' in codes:
        body = f'{oid} has not been delivered yet, so a return or replacement is not possible at this stage.'
    elif codes & {'IDENTITY_MISMATCH', 'CROSS_TENANT_ORDER', 'ORDER_NOT_FOUND'}:
        body = f'We could not find {oid} on your account. Please check the order number and reply so we can help.'
    else:
        body = f'We are unable to complete this request for {oid}.'
    return f'Hello {name}, thank you for contacting {brand}. {body} Kind regards, {brand} Support'


def run(data):
    as_of, ticket, requester, systems, limits = agent_module.validate(data)
    text = ticket['text']
    intent = classify(text)
    order_ids = [m.upper() for m in ORDER_ID.findall(text)]
    order_id = order_ids[0] if order_ids else ''
    order, reason = policy.find_order(systems, order_id, ticket['customer_id'], ticket['tenant_id'])
    skus = affected_skus(text, order) if intent in ('refund', 'return', 'replace') else []
    flags = ['PROMPT_INJECTION'] if INJECTION.search(text) else []
    decision = policy.decide(intent, order_id, order, reason, systems['policies'], ticket['tenant_id'], requester['role'], limits, as_of, skus, flags)
    visible = policy.visible_sections(systems['policies'], ticket['tenant_id'], requester['role'], as_of)
    hidden = policy.hidden_sections(systems['policies'], ticket['tenant_id'], requester['role'], as_of)
    by_id = {s['section_id']: s for s in visible}
    cited_raw = []
    for sid in decision['policy_refs']:
        if sid in by_id:
            cited_raw.append({'policy_id': by_id[sid]['policy_id'], 'section_id': sid, 'quote': policy.sentences(by_id[sid]['text'])[0]})
            break
    cited, citation_codes = policy.check_citations(cited_raw, visible, hidden)
    customer = next(c for c in systems['customers'] if c['id'] == ticket['customer_id'])
    brand = {'T-A': 'Northwind Outdoor', 'T-B': 'Lumen Home'}.get(ticket['tenant_id'], 'our store')
    reply = template_reply(brand, customer['name'].split()[0], decision, order, limits['currency'])
    if cited:
        reply = reply.replace(' Kind regards', f" Our policy states: \"{cited[0]['quote']}\" Kind regards")
    reply_codes, reply_status = policy.reply_checks(reply, decision, cited, hidden, visible)
    output = policy.build_output(ticket, requester, intent, decision, cited, reply, reply_status, [], extra_findings=citation_codes + reply_codes,
                                 currency=limits['currency'])
    output['baseline'] = 'keyword-macro'
    return output
