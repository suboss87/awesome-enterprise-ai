"""Deterministic order-entry rules: customer, ship-to and part resolution, price, unit of measure,
MOQ, stock, duplicates, credit, route.

The model reads the customer's document and records what it says, line by line, each line with a
verbatim quote. This module decides everything else. The agent and the baseline call the same
functions, so any difference in results comes from the reading step.

Conventions:
  * A part resolves from the customer's cross-reference, then the internal SKU, then the description.
    Description resolution reads the line quote, not the model's paraphrase: the quote must contain
    at least 75% of the words of exactly one price-list description. Two descriptions within 0.10
    of the best score make the line ambiguous.
  * Sales quantities are in the price list's unit (EA or CS). A line in the other unit is converted
    with the item's pack size. Eaches that do not fill whole cases are a UOM_MISMATCH.
  * Price variance = (PO unit price converted to the sales unit - list price) / list price, in percent,
    rounded half-up to two decimals before the tolerance test. The order is always priced at list.
  * The order total for credit and approval is quantity x list price. The PO total is checked
    against the PO's own printed lines (quantity x printed price), with 0.05 rounding tolerance.
"""
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from enterprise_ai.common import InputError

ROUTES = ('auto_create', 'desk_review', 'reject')
DOCUMENT_TYPES = ('purchase_order', 'rfq', 'quote_acceptance', 'order_acknowledgement', 'other')
CODES = ['NOT_AN_ORDER', 'DUPLICATE_PO', 'UNKNOWN_CUSTOMER', 'CREDIT_HOLD', 'CREDIT_LIMIT_EXCEEDED', 'OVER_APPROVAL_LIMIT',
         'SHIP_TO_UNKNOWN', 'UNKNOWN_PART', 'AMBIGUOUS_PART', 'UOM_MISMATCH', 'PRICE_MISMATCH', 'BELOW_MOQ',
         'INSUFFICIENT_STOCK', 'DUPLICATE_SUSPECTED', 'TOTAL_MISMATCH', 'UNGROUNDED_LINE', 'PROMPT_INJECTION']
MODEL_ONLY = {'PROMPT_INJECTION'}
REJECT = {'NOT_AN_ORDER', 'DUPLICATE_PO'}
UNITS = ('EA', 'CS')
UOM_ALIASES = {'EA': {'ea', 'each', 'eaches', 'unit', 'units', 'pc', 'pcs', 'piece', 'pieces'},
               'CS': {'cs', 'case', 'cases', 'ctn', 'carton', 'cartons'}}
CENT = Decimal('0.01')
ROUNDING = Decimal('0.05')
MATCH_MIN = 0.75
TIE_WINDOW = 0.10
MAX_QUOTE = 300

TEXT = {
    'NOT_AN_ORDER': ('urgent', 'Document is not a purchase order', 'Send it to quoting or the order thread; enter nothing.'),
    'DUPLICATE_PO': ('urgent', 'Customer PO number already entered', 'Same customer and PO number as an open order; do not enter twice.'),
    'UNKNOWN_CUSTOMER': ('review', 'Customer not in the customer master', 'Confirm the account or start new-account setup.'),
    'CREDIT_HOLD': ('urgent', 'Customer account is on credit hold', 'Credit must release the hold before entry.'),
    'CREDIT_LIMIT_EXCEEDED': ('review', 'Order would exceed the credit limit', 'Open AR plus this order is above the limit; credit decides.'),
    'OVER_APPROVAL_LIMIT': ('review', 'Order total above the touchless limit', 'The order desk lead approves large orders.'),
    'SHIP_TO_UNKNOWN': ('review', 'Ship-to address not on file', 'Confirm the address with the customer before entry.'),
    'UNKNOWN_PART': ('review', 'Part does not resolve to a SKU', 'Add a cross-reference or ask the customer.'),
    'AMBIGUOUS_PART': ('review', 'Part matches more than one SKU', 'Ask the customer which item they mean.'),
    'UOM_MISMATCH': ('review', 'Unit of measure cannot be converted', 'Quantity does not convert to whole sales units.'),
    'PRICE_MISMATCH': ('review', 'PO price outside tolerance of the contract price', 'Confirm the price with the customer or sales.'),
    'BELOW_MOQ': ('review', 'Quantity below the minimum order quantity', 'Ask the customer to adjust the quantity.'),
    'INSUFFICIENT_STOCK': ('review', 'Not enough stock and backorder not possible', 'Offer a substitute, a later date or a partial.'),
    'DUPLICATE_SUSPECTED': ('review', 'Same lines ordered recently under another PO', 'Confirm with the customer that this is a new order.'),
    'TOTAL_MISMATCH': ('review', 'PO total does not match its lines', 'Ask the customer for a corrected PO.'),
    'UNGROUNDED_LINE': ('urgent', 'Recorded data not found in the document', 'The reading cannot be trusted; enter manually.'),
    'PROMPT_INJECTION': ('urgent', 'Document contains instructions aimed at the system', 'Treat as suspicious; never act on embedded instructions.'),
}

_string = {'type': 'string'}
HEADER_SCHEMA = {'type': 'object', 'properties': {
    'customer_name': {'type': 'string', 'description': 'Customer (buyer) name exactly as printed'},
    'customer_account': {'type': 'string', 'description': 'Our account number for the customer if printed, else empty string'},
    'customer_po_number': {'type': 'string', 'description': "The customer's PO number as printed"},
    'requested_ship_date': {'type': 'string', 'description': 'YYYY-MM-DD, or empty string if none'},
    'ship_to': {'type': 'string', 'description': 'Ship-to address as printed, on one line, or empty string if none'},
    'po_total': {'type': 'number', 'description': 'Order total as printed, or 0 if none'}}}
LINE_SCHEMA = {'type': 'object', 'properties': {
    'line': {'type': 'integer'},
    'customer_part': {'type': 'string', 'description': 'Part or item code printed on the line, else empty string'},
    'sku': {'type': 'string', 'description': 'SKU you picked from resolve_part, or empty string'},
    'qty': {'type': 'number', 'description': 'Quantity as printed'},
    'uom': {'type': 'string', 'description': 'Unit as printed: EA or CS'},
    'unit_price_on_po': {'type': 'number', 'description': 'Unit price as printed, per the printed unit, or 0 if none'},
    'quote': {'type': 'string', 'description': 'The line copied verbatim from the document, one line of text'}}}
RECORD_SCHEMA = {'type': 'object', 'properties': {'header': HEADER_SCHEMA, 'lines': {'type': 'array', 'items': LINE_SCHEMA}}}


def dec(value):
    return Decimal(str(value))


def cents(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def tokens(text):
    return re.findall(r'[a-z0-9]+', str(text).lower())


def code_key(code):
    return re.sub(r'[^A-Z0-9]', '', str(code).upper())


def shows(text, value):
    """True when `text` prints the number: 1,234.50 / 1234.50 / 1234.5, or 24 for whole numbers."""
    v = dec(value)
    forms = {f'{v:,.2f}', f'{v:.2f}', format(v.normalize(), 'f')}
    if v == v.to_integral_value():
        forms |= {f'{int(v):,}', str(int(v))}
    return any(re.search(r'(?<![\d.,])' + re.escape(f) + r'(?!\d|[.,]\d)', text) for f in forms)


def unit(printed):
    word = str(printed).strip().lower().rstrip('.')
    return next((u for u, names in UOM_ALIASES.items() if word in names), None)


# ---- master data lookups -------------------------------------------------------------------

NAME_STOP = {'inc', 'llc', 'ltd', 'co', 'corp', 'corporation', 'company', 'the', 'and'}
ADDRESS_ABBREV = {'street': 'st', 'avenue': 'ave', 'road': 'rd', 'drive': 'dr', 'boulevard': 'blvd', 'suite': 'ste',
                  'parkway': 'pkwy', 'lane': 'ln', 'highway': 'hwy', 'court': 'ct', 'place': 'pl'}


def customer_by_id(erp, customer_id):
    return next((c for c in erp['customers'] if c['customer_id'] == customer_id), None)


def find_customer(erp, name='', account=''):
    """Exact account number first, then token overlap on the name (>= 0.6). Returns (customer, how)."""
    key = code_key(account)
    if key:
        for customer in erp['customers']:
            if code_key(customer['customer_id']) == key:
                return customer, 'account'
    wanted = set(tokens(name)) - NAME_STOP
    best, best_score = None, 0.0
    for customer in erp['customers']:
        have = set(tokens(customer['name'])) - NAME_STOP
        score = len(wanted & have) / max(len(wanted), len(have), 1)
        if score > best_score:
            best, best_score = customer, score
    if best is not None and best_score >= 0.6:
        return best, f'name:{best_score:.2f}'
    return None, 'no_match'


def address_key(text):
    return frozenset(ADDRESS_ABBREV.get(t, t) for t in tokens(text))


def find_ship_to(customer, printed):
    """Printed address equal to one on file after normalization; no address printed means the default (first)."""
    if not str(printed).strip():
        return customer['ship_to_addresses'][0], 'default'
    key = address_key(printed)
    for address in customer['ship_to_addresses']:
        if address_key(address['address']) == key:
            return address, 'address'
    return None, 'not_on_file'


def price_items(erp, customer):
    price_list = next(p for p in erp['price_lists'] if p['price_list_id'] == customer['price_list_id'])
    return {item['sku']: item for item in price_list['items']}


def resolve_part(erp, customer, customer_part, line_text):
    """Candidates for one PO line. status: cross_reference | sku | description | ambiguous | unknown."""
    items = price_items(erp, customer)
    part = code_key(customer_part)
    if part:
        for xref in erp['customer_part_numbers']:
            if xref['customer_id'] == customer['customer_id'] and code_key(xref['customer_part']) == part:
                if xref['sku'] in items:
                    return {'status': 'cross_reference', 'sku': xref['sku'], 'candidates': [_candidate(items[xref['sku']], 1.0)]}
                return {'status': 'unknown', 'sku': None, 'candidates': [], 'reason': 'cross-reference SKU not on the price list'}
        for sku, item in items.items():
            if code_key(sku) == part:
                return {'status': 'sku', 'sku': sku, 'candidates': [_candidate(item, 1.0)]}
        return {'status': 'unknown', 'sku': None, 'candidates': [], 'reason': f'part {customer_part} is not cross-referenced'}
    words = set(tokens(line_text))
    scored = []
    for item in items.values():
        desc = set(tokens(item['description']))
        score = round(len(desc & words) / len(desc), 3) if desc else 0.0
        if score >= MATCH_MIN:
            scored.append(_candidate(item, score))
    scored.sort(key=lambda c: (-c['score'], c['sku']))
    if not scored:
        return {'status': 'unknown', 'sku': None, 'candidates': [], 'reason': 'no price-list description matches the line'}
    close = [c for c in scored if c['score'] >= scored[0]['score'] - TIE_WINDOW]
    if len(close) > 1:
        return {'status': 'ambiguous', 'sku': None, 'candidates': close}
    return {'status': 'description', 'sku': scored[0]['sku'], 'candidates': scored}


def _candidate(item, score):
    return {'sku': item['sku'], 'description': item['description'], 'uom': item['uom'], 'score': score}


def inventory_for(erp, sku):
    return next((i for i in erp['inventory'] if i['sku'] == sku), None)


def open_order_matches(erp, customer_id, po_number, line_keys, as_of, window_days):
    """Exact: same customer and PO number. Similar: same customer, same (sku, qty) lines, created within the window."""
    key = code_key(po_number)
    exact, similar = [], []
    for order in erp['open_orders']:
        if order['customer_id'] != customer_id:
            continue
        if key and code_key(order['customer_po_number']) == key:
            exact.append(order)
            continue
        age = (as_of - date.fromisoformat(order['created_on'])).days
        if line_keys and 0 <= age <= window_days and sorted((l['sku'], dec(l['qty'])) for l in order['lines']) == line_keys:
            similar.append(order)
    return exact, similar


# ---- recording -----------------------------------------------------------------------------

def normalize_recording(raw):
    """Validate what the reader recorded. Raises InputError so the model can correct and record again."""
    header, lines = raw['header'], raw['lines']
    when = header['requested_ship_date'].strip()
    if when:
        try:
            if date.fromisoformat(when).isoformat() != when:
                raise ValueError
        except ValueError as exc:
            raise InputError('requested_ship_date must be YYYY-MM-DD or empty') from exc
    if type(header['po_total']) not in (int, float) or not 0 <= header['po_total'] <= 1e9:
        raise InputError('po_total must be a non-negative amount (0 when not printed)')
    if not 1 <= len(lines) <= 200:
        raise InputError('Record between 1 and 200 lines')
    for line in lines:
        if type(line['qty']) not in (int, float) or not 0 < line['qty'] <= 1e6:
            raise InputError(f"Line {line['line']}: qty must be a positive number")
        if type(line['unit_price_on_po']) not in (int, float) or not 0 <= line['unit_price_on_po'] <= 1e6:
            raise InputError(f"Line {line['line']}: unit_price_on_po must be a non-negative number (0 when not printed)")
        if not line['quote'].strip():
            raise InputError(f"Line {line['line']}: quote the line verbatim")
    return {'header': dict(header), 'lines': [dict(l) for l in lines]}


def _sources(document):
    return [document['text']] + ([document['email_body']] if document.get('email_body') else [])


def _in_sources(fragment, sources):
    fragment = re.sub(r'\s+', ' ', str(fragment)).strip().lower()
    return bool(fragment) and any(fragment in re.sub(r'\s+', ' ', s).lower() for s in sources)


def _grounding(line, sources):
    quote = line['quote']
    if '\n' in quote or len(quote) > MAX_QUOTE or not any(quote in s for s in sources):
        return 'quote is not one verbatim line of the document'
    if not shows(quote, line['qty']):
        return 'quote does not print the quantity'
    if line['unit_price_on_po'] and not shows(quote, line['unit_price_on_po']):
        return 'quote does not print the unit price'
    if line['customer_part'].strip() and line['customer_part'].strip().lower() not in quote.lower():
        return 'quote does not print the part number'
    return None


def to_sales_qty(qty, printed_uom, item):
    """(sales quantity as int, note) or (None, reason)."""
    printed = unit(printed_uom)
    if printed is None:
        return None, f'unit {printed_uom!r} is not EA or CS'
    q, pack = dec(qty), dec(item['pack_size'])
    if printed == item['uom']:
        n = q
    elif printed == 'CS':
        n = q * pack
    else:
        n = q / pack
    if n != n.to_integral_value() or n <= 0:
        return None, f"{qty} {printed} is not a whole number of {item['uom']} (pack size {item['pack_size']})"
    return int(n), ''


def check_line(raw, erp, customer, policy, sources):
    """Evaluate one recorded line. Returns the line detail with its issue codes."""
    out = {'line': raw['line'], 'quote': raw['quote'], 'customer_part': raw['customer_part'], 'model_sku': raw['sku'],
           'printed_qty': raw['qty'], 'printed_uom': raw['uom'], 'unit_price_on_po': raw['unit_price_on_po'],
           'sku': None, 'qty': None, 'uom': None, 'unit_price': None, 'extended': None, 'price_variance_pct': None,
           'ship_now_qty': None, 'backorder_qty': None, 'backorder_date': None, 'issues': [], 'notes': []}
    problem = _grounding(raw, sources)
    out['grounded'] = problem is None
    if problem:
        out['issues'].append('UNGROUNDED_LINE')
        out['notes'].append(problem)
    resolution = resolve_part(erp, customer, raw['customer_part'], raw['quote'])
    out['resolution'] = resolution['status']
    out['candidates'] = [c['sku'] for c in resolution['candidates']]
    if resolution['status'] == 'unknown':
        out['issues'].append('UNKNOWN_PART')
        out['notes'].append(resolution['reason'])
        return out
    if resolution['status'] == 'ambiguous':
        out['issues'].append('AMBIGUOUS_PART')
        out['notes'].append('candidates ' + ', '.join(out['candidates']))
        return out
    sku = resolution['sku']
    if raw['sku'].strip() and code_key(raw['sku']) != code_key(sku):
        out['issues'].append('AMBIGUOUS_PART')
        out['notes'].append(f"reader picked {raw['sku']}, rules resolved {sku}")
        return out
    item = price_items(erp, customer)[sku]
    list_price = cents(dec(item['unit_price']))
    out.update({'sku': sku, 'uom': item['uom'], 'unit_price': list_price})
    qty, reason = to_sales_qty(raw['qty'], raw['uom'], item)
    if qty is None:
        out['issues'].append('UOM_MISMATCH')
        out['notes'].append(reason)
        return out
    out['qty'] = qty
    out['extended'] = cents(list_price * qty)
    if raw['unit_price_on_po']:
        per_sales_unit = dec(raw['unit_price_on_po']) * dec(raw['qty']) / qty
        variance = cents((per_sales_unit - list_price) / list_price * 100) if list_price else Decimal(0)
        out['price_variance_pct'] = variance
        if abs(variance) > dec(policy['price_tolerance_pct']):
            out['issues'].append('PRICE_MISMATCH')
            out['notes'].append(f'PO price {per_sales_unit:.4f} per {item["uom"]} vs list {list_price} ({variance}%)')
    if qty < item['moq']:
        out['issues'].append('BELOW_MOQ')
        out['notes'].append(f"{qty} {item['uom']} below MOQ {item['moq']}")
    stock = inventory_for(erp, sku) or {'available_qty': 0, 'next_receipt_date': None}
    available = max(0, int(stock['available_qty']))
    if qty <= available:
        out['ship_now_qty'], out['backorder_qty'] = qty, 0
    elif policy['backorder_allowed'] and stock['next_receipt_date']:
        out['ship_now_qty'] = available if policy['partial_ship_allowed'] else 0
        out['backorder_qty'] = qty - out['ship_now_qty']
        out['backorder_date'] = stock['next_receipt_date']
        out['notes'].append(f"{qty - available} short; backorder until {stock['next_receipt_date']}")
    else:
        out['issues'].append('INSUFFICIENT_STOCK')
        out['notes'].append(f'{available} available of {qty}' + ('' if policy['backorder_allowed'] else '; backorders not allowed'))
    return out


# ---- the decision --------------------------------------------------------------------------

def assess(data, document_type, recording, model_flags=()):
    """Return the verdict: route, ordered codes with details, customer, ship-to and evaluated lines."""
    erp, policy, document = data['erp'], data['policy'], data['document']
    found, lines, customer, ship_to = {}, [], None, None
    header = recording['header'] if recording else {}
    for flag in model_flags:
        if flag in MODEL_ONLY:
            found.setdefault(flag, 'Reported by the reading step')
    if document_type != 'purchase_order':
        found['NOT_AN_ORDER'] = f'Document read as {document_type}'
        return _verdict(found, header, None, None, [], None)
    if recording is None:
        found['UNGROUNDED_LINE'] = 'No order lines were recorded'
        return _verdict(found, header, None, None, [], None)
    sources = _sources(document)
    customer, how = find_customer(erp, header['customer_name'], header['customer_account'])
    printed = [v for v in (header['customer_name'], header['customer_account']) if v.strip()]
    if customer is not None and not any(_in_sources(v, sources) for v in printed):
        customer, how = None, 'name and account not printed in the document'
    if customer is None:
        found['UNKNOWN_CUSTOMER'] = f"{header['customer_name'] or 'No customer name'}: {how}"
        return _verdict(found, header, None, None, [], None)
    if customer['on_hold']:
        found['CREDIT_HOLD'] = f"{customer['customer_id']} is on hold"
    ship_to, how = find_ship_to(customer, header['ship_to'])
    if ship_to is not None and how == 'address' and not set(tokens(header['ship_to'])) <= set(tokens(' '.join(sources))):
        ship_to, how = None, 'address not printed in the document'
    if ship_to is None:
        found['SHIP_TO_UNKNOWN'] = f"{header['ship_to']}: {how}"
    if not _in_sources(header['customer_po_number'], sources):
        found['UNGROUNDED_LINE'] = 'PO number missing or not printed in the document'
    for raw in recording['lines']:
        line = check_line(raw, erp, customer, policy, sources)
        lines.append(line)
        for code in line['issues']:
            found.setdefault(code, '')
            found[code] = '; '.join(filter(None, [found[code], f"line {line['line']}: " + '; '.join(line['notes'])]))
    if header['po_total']:
        if not shows('\n'.join(sources), header['po_total']):
            found.setdefault('UNGROUNDED_LINE', 'PO total not printed in the document')
        printed_sum = sum((cents(dec(l['qty']) * dec(l['unit_price_on_po'])) for l in recording['lines']), Decimal(0))
        if abs(printed_sum - cents(dec(header['po_total']))) > ROUNDING:
            found['TOTAL_MISMATCH'] = f"Lines add up to {printed_sum}, PO total {cents(dec(header['po_total']))}"
    priced = [l for l in lines if l['extended'] is not None]
    total = sum((l['extended'] for l in priced), Decimal(0))
    keys = sorted((l['sku'], dec(l['qty'])) for l in lines) if lines and len(priced) == len(lines) else None
    exact, similar = open_order_matches(erp, customer['customer_id'], header['customer_po_number'], keys,
                                        date.fromisoformat(data['as_of']), policy['duplicate_window_days'])
    if exact:
        found['DUPLICATE_PO'] = 'Open order ' + ', '.join(o['order_id'] for o in exact)
    elif similar:
        found['DUPLICATE_SUSPECTED'] = 'Same lines as ' + ', '.join(f"{o['order_id']} (PO {o['customer_po_number']}, {o['created_on']})" for o in similar)
    if total > dec(policy['credit_check_required_above']):
        exposure = dec(customer['open_ar_balance']) + total
        if exposure > dec(customer['credit_limit']):
            found['CREDIT_LIMIT_EXCEEDED'] = f"Open AR {customer['open_ar_balance']:,.2f} + order {total:,.2f} > limit {customer['credit_limit']:,.2f}"
    if total > dec(policy['max_order_total_without_approval']):
        found['OVER_APPROVAL_LIMIT'] = f"Order total {total:,.2f} above {policy['max_order_total_without_approval']:,.2f}"
    return _verdict(found, header, customer, ship_to, lines, total)


def decide_route(codes):
    if set(codes) & REJECT:
        return 'reject'
    return 'desk_review' if codes else 'auto_create'


def _verdict(found, header, customer, ship_to, lines, total):
    codes = [c for c in CODES if c in found]
    return {'route': decide_route(codes), 'codes': codes, 'details': found, 'header': header, 'customer': customer,
            'ship_to': ship_to, 'lines': lines, 'total': total}


# ---- shared output -------------------------------------------------------------------------

def to_json(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: to_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_json(v) for v in value]
    return value


def build_output(data, verdict, document_type, drafted_query, evidence):
    """Shared output shape for the agent and the baseline."""
    doc_id = data['document']['id']
    route, codes = verdict['route'], verdict['codes']
    findings = [{'code': c, 'severity': TEXT[c][0], 'title': TEXT[c][1],
                 'detail': (verdict['details'][c] + '. ' if verdict['details'][c] else '') + TEXT[c][2], 'evidence_ids': [doc_id]}
                for c in codes]
    customer, header = verdict['customer'], verdict['header']
    order = {'customer_id': customer['customer_id'] if customer else None, 'customer_name': customer['name'] if customer else None,
             'customer_po_number': header.get('customer_po_number'), 'requested_ship_date': header.get('requested_ship_date') or None,
             'ship_to_id': verdict['ship_to']['id'] if verdict['ship_to'] else None,
             'payment_terms': customer['payment_terms'] if customer else None,
             'lines': [to_json({k: l[k] for k in ('line', 'sku', 'qty', 'uom', 'unit_price', 'extended', 'ship_now_qty', 'backorder_qty',
                                                 'backorder_date', 'resolution', 'candidates', 'model_sku', 'customer_part', 'printed_qty',
                                                 'printed_uom', 'unit_price_on_po', 'price_variance_pct', 'issues', 'notes', 'grounded', 'quote')})
                       for l in verdict['lines']],
             'total': to_json(verdict['total'])}
    if route == 'auto_create':
        actions = [{'action': 'create_sales_order', 'owner': 'Order desk automation', 'status': 'awaiting_approval',
                    'customer_id': order['customer_id'], 'customer_po_number': order['customer_po_number'], 'total': order['total'],
                    'note': 'All checks passed. The configured release step creates the order in the ERP.'}]
    elif route == 'desk_review':
        actions = [{'action': 'desk_review', 'owner': 'Order desk rep', 'approver': 'Order desk lead', 'status': 'queued', 'codes': codes}]
        if drafted_query:
            actions.append({'action': 'send_customer_query', 'owner': 'Order desk rep', 'status': 'draft', 'draft': drafted_query})
    else:
        actions = [{'action': 'reject_and_notify', 'owner': 'Order desk rep', 'status': 'queued', 'codes': codes}]
    summary = {'auto_create': f"Order ready: {len(order['lines'])} lines, total {order['total']:,.2f}, all checks passed." if order['total'] is not None else 'Order ready.',
               'desk_review': f"Order needs the desk: {', '.join(codes)}.",
               'reject': f"Not entered: {', '.join(codes)}."}[route]
    return {'project': 'order-entry-agent', 'summary': summary,
            'metrics': {'route': route, 'finding_count': len(codes), 'line_count': len(order['lines']), 'order_total': order['total'],
                        'customer_id': order['customer_id']},
            'findings': findings, 'actions': actions, 'document_type': document_type, 'order': order, 'evidence': evidence}
