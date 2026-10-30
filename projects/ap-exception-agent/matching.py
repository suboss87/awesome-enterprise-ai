"""Deterministic accounts-payable rules: vendor lookup, 3-way match, duplicates, route.

The model extracts and reads. This module decides. Both the agent and the baseline
call the same functions, so any difference in results comes from the reading step.
Amounts are decimals in major units (e.g. 1234.50 USD). Rounding tolerance 0.05.
"""
import re
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from enterprise_ai.common import InputError

ROUNDING = Decimal('0.05')
FLAG_ORDER = ['NOT_AN_INVOICE', 'DUPLICATE_INVOICE', 'DUPLICATE_SUSPECTED', 'UNKNOWN_VENDOR', 'NO_PO', 'PO_VENDOR_MISMATCH',
              'CURRENCY_MISMATCH', 'PRICE_VARIANCE', 'QTY_EXCEEDS_RECEIPT', 'NO_RECEIPT', 'UNMATCHED_LINE',
              'ARITHMETIC_MISMATCH', 'TAX_MISCALCULATED', 'BANK_DETAILS_CHANGED', 'OVER_LIMIT',
              'PROMPT_INJECTION', 'SUSPICIOUS_REQUEST']
MODEL_ONLY_FLAGS = {'PROMPT_INJECTION', 'SUSPICIOUS_REQUEST'}
REJECT_FLAGS = {'NOT_AN_INVOICE', 'DUPLICATE_INVOICE'}

EXTRACTED_SCHEMA = {
    'type': 'object',
    'properties': {
        'vendor_name': {'type': 'string', 'description': 'Supplier name as printed'},
        'vendor_tax_id': {'type': 'string', 'description': 'VAT/tax id as printed, or empty string'},
        'invoice_number': {'type': 'string'},
        'invoice_date': {'type': 'string', 'description': 'ISO date YYYY-MM-DD'},
        'po_numbers': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Every purchase order referenced; empty if none'},
        'currency': {'type': 'string', 'description': 'Three-letter code'},
        'lines': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'po_number': {'type': 'string', 'description': 'PO this line bills, or empty string'},
            'sku': {'type': 'string', 'description': 'Item code if printed, else empty string'},
            'description': {'type': 'string'},
            'qty': {'type': 'number'},
            'unit_price': {'type': 'number'},
            'line_total': {'type': 'number'}}}},
        'subtotal': {'type': 'number'},
        'tax_total': {'type': 'number'},
        'gross_total': {'type': 'number'},
        'bank_iban': {'type': 'string', 'description': 'Bank account/IBAN printed on the document or in the covering email, else empty string'},
    },
}


def money(value):
    try:
        return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except Exception as exc:  # noqa: BLE001
        raise InputError(f'Invalid amount {value!r}') from exc


def normalize_name(name):
    name = re.sub(r'[^a-z0-9 ]', ' ', str(name).lower())
    stop = {'ltd', 'limited', 'llc', 'inc', 'gmbh', 'co', 'company', 'corp', 'corporation', 'plc', 'sa', 'bv', 'the', 'and'}
    return [t for t in name.split() if t and t not in stop]


def find_vendor(erp, name='', tax_id=''):
    """Exact tax id first, then token overlap on the name. Returns (vendor, how) or (None, reason)."""
    tax_id = re.sub(r'\s', '', str(tax_id or '')).upper()
    if tax_id:
        for vendor in erp['vendors']:
            if re.sub(r'\s', '', vendor.get('tax_id', '')).upper() == tax_id:
                return vendor, 'tax_id'
    tokens = set(normalize_name(name))
    if not tokens:
        return None, 'no_name'
    best, best_score = None, 0.0
    for vendor in erp['vendors']:
        vt = set(normalize_name(vendor['name']))
        if not vt:
            continue
        score = len(tokens & vt)/max(len(tokens), len(vt))
        if score > best_score:
            best, best_score = vendor, score
    if best and best_score >= 0.6:
        return best, f'name:{best_score:.2f}'
    return None, 'no_match'


def find_po(erp, po_number):
    po_number = str(po_number or '').strip().upper()
    for po in erp['purchase_orders']:
        if po['po_number'].upper() == po_number:
            return po
    return None


def receipts_for(erp, po_number):
    return [g for g in erp['goods_receipts'] if g['po_number'].upper() == str(po_number).upper()]


def accepted_by_line(erp, po_number):
    totals = {}
    for grn in receipts_for(erp, po_number):
        for line in grn['lines']:
            totals[line['po_line']] = totals.get(line['po_line'], 0) + line['qty_accepted']
    return totals


def ledger_matches(erp, vendor_id, invoice_number, gross_total, invoice_date=None):
    """Exact: same vendor and invoice number. Suspected: same vendor and amount within
    30 days, or invoice numbers that differ by one transposition or one character."""
    exact, suspected = [], []
    number = re.sub(r'\W', '', str(invoice_number or '')).upper()
    total = money(gross_total) if gross_total not in (None, '') else None
    when = _parse_date(invoice_date) if invoice_date else None
    for entry in erp['ap_ledger']:
        if entry['vendor_id'] != vendor_id:
            continue
        candidate = re.sub(r'\W', '', entry['invoice_number']).upper()
        if candidate == number:
            exact.append(entry)
            continue
        same_amount = total is not None and money(entry['gross_total']) == total
        close_date = True
        if when and entry.get('invoice_date'):
            close_date = abs((_parse_date(entry['invoice_date']) - when).days) <= 30
        if same_amount and close_date and (_near(candidate, number) or close_date):
            suspected.append(entry)
    return exact, suspected


def _near(a, b):
    if len(a) != len(b):
        return False
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    if len(diff) == 1:
        return True
    return len(diff) == 2 and diff[1] == diff[0]+1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]


def _parse_date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise InputError(f'Invalid date {value!r}') from exc


def match(extracted, erp, policy, document_type='invoice', model_flags=(), risk_notes=()):
    """Return {'flags': [...], 'route': ..., 'vendor': ..., 'details': {...}}."""
    flags, details = set(), {}
    if document_type != 'invoice':
        flags.add('NOT_AN_INVOICE')
    vendor, how = find_vendor(erp, extracted.get('vendor_name', ''), extracted.get('vendor_tax_id', ''))
    details['vendor_match'] = how
    if vendor is None:
        flags.add('UNKNOWN_VENDOR')
    currency = str(extracted.get('currency', '')).upper()
    if currency and currency != policy['currency']:
        flags.add('CURRENCY_MISMATCH')
    po_numbers = [str(p).strip().upper() for p in extracted.get('po_numbers', []) if str(p).strip()]
    pos = {p: find_po(erp, p) for p in po_numbers}
    if not po_numbers or any(po is None for po in pos.values()):
        flags.add('NO_PO')
        details['missing_pos'] = [p for p, po in pos.items() if po is None]
    if vendor is not None:
        for po in pos.values():
            if po is not None and po['vendor_id'] != vendor['vendor_id']:
                flags.add('PO_VENDOR_MISMATCH')
    lines = extracted.get('lines', [])
    line_sum = sum((money(l['line_total']) for l in lines), Decimal('0'))
    subtotal = money(extracted.get('subtotal', 0))
    tax = money(extracted.get('tax_total', 0))
    gross = money(extracted.get('gross_total', 0))
    if lines and abs(line_sum - subtotal) > ROUNDING:
        flags.add('ARITHMETIC_MISMATCH')
    if abs(subtotal + tax - gross) > ROUNDING:
        flags.add('ARITHMETIC_MISMATCH')
    expected_tax = (subtotal * Decimal(str(policy['tax_rate_pct'])) / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if abs(expected_tax - tax) > ROUNDING:
        flags.add('TAX_MISCALCULATED')
    details['expected_tax'] = str(expected_tax)
    # Three-way match per line.
    unit_tol = Decimal(str(policy['unit_price_tolerance_pct']))
    matched_lines = []
    billed_by_po_line = {}
    for line in lines:
        tag = str(line.get('po_number', '')).strip().upper()
        candidates = [pos[tag]] if tag and pos.get(tag) else [p for p in pos.values() if p is not None]
        po, po_line = None, None
        for candidate in candidates:
            po_line = _match_po_line(candidate, line)
            if po_line is not None:
                po = candidate
                break
        if not candidates:
            matched_lines.append({'description': line.get('description'), 'status': 'no_po'})
            continue
        if po_line is None:
            po = candidates[0]
            flags.add('UNMATCHED_LINE')
            matched_lines.append({'description': line.get('description'), 'status': 'unmatched'})
            continue
        unit_price = money(line['unit_price'])
        po_price = money(po_line['unit_price'])
        variance_pct = (unit_price - po_price) / po_price * 100 if po_price else Decimal('0')
        status = 'ok'
        if abs(variance_pct) > unit_tol:
            flags.add('PRICE_VARIANCE')
            status = 'price_variance'
        key = (po['po_number'], po_line['line'])
        billed_by_po_line[key] = billed_by_po_line.get(key, 0) + float(line['qty'])
        matched_lines.append({'po_number': po['po_number'], 'po_line': po_line['line'], 'qty_billed': line['qty'],
                              'unit_price': str(unit_price), 'po_unit_price': str(po_price),
                              'variance_pct': str(variance_pct.quantize(Decimal('0.01'))), 'status': status})
    for (po_number, line_no), qty in billed_by_po_line.items():
        accepted = accepted_by_line(erp, po_number)
        if not receipts_for(erp, po_number):
            flags.add('NO_RECEIPT')
        elif qty > accepted.get(line_no, 0) + 1e-9:
            flags.add('QTY_EXCEEDS_RECEIPT')
        for entry in matched_lines:
            if entry.get('po_number') == po_number and entry.get('po_line') == line_no:
                entry['qty_accepted'] = accepted.get(line_no, 0)
    details['lines'] = matched_lines
    if vendor is not None:
        exact, suspected = ledger_matches(erp, vendor['vendor_id'], extracted.get('invoice_number'), extracted.get('gross_total'), extracted.get('invoice_date'))
        if exact:
            flags.add('DUPLICATE_INVOICE')
            details['duplicate_of'] = [e['invoice_number'] for e in exact]
        elif suspected:
            flags.add('DUPLICATE_SUSPECTED')
            details['similar_to'] = [e['invoice_number'] for e in suspected]
        iban = re.sub(r'\s', '', str(extracted.get('bank_iban', ''))).upper()
        if iban and iban != re.sub(r'\s', '', vendor.get('bank_iban', '')).upper():
            flags.add('BANK_DETAILS_CHANGED')
    if gross > Decimal(str(policy['auto_approve_limit'])):
        flags.add('OVER_LIMIT')
    for flag in model_flags:
        if flag in MODEL_ONLY_FLAGS:
            flags.add(flag)
    details['risk_notes'] = list(risk_notes)
    ordered = [f for f in FLAG_ORDER if f in flags]
    if flags & REJECT_FLAGS:
        route = 'reject'
    elif ordered:
        route = 'human_review'
    else:
        route = 'auto_approve'
    return {'flags': ordered, 'route': route, 'vendor': vendor, 'details': details,
            'gross_total': str(gross), 'currency': currency or policy['currency']}


def _match_po_line(po, line):
    sku = str(line.get('sku', '')).strip().upper()
    if sku:
        for po_line in po['lines']:
            if po_line.get('sku', '').upper() == sku:
                return po_line
    tokens = set(normalize_name(line.get('description', '')))
    best, best_score = None, 0.0
    for po_line in po['lines']:
        pt = set(normalize_name(po_line['description']))
        score = len(tokens & pt)/max(1, len(tokens | pt))
        if score > best_score:
            best, best_score = po_line, score
    return best if best_score >= 0.34 else None


def build_output(extracted, verdict, document_type, drafted_query, evidence, source):
    """Shared output shape for the agent and the baseline."""
    findings = []
    text = {
        'NOT_AN_INVOICE': ('urgent', 'Document is not an invoice', 'Route to the right process instead of accounts payable.'),
        'DUPLICATE_INVOICE': ('urgent', 'Duplicate of a posted invoice', 'Same vendor and invoice number already in the ledger.'),
        'DUPLICATE_SUSPECTED': ('review', 'Possible duplicate', 'Same vendor and amount, similar number or date.'),
        'UNKNOWN_VENDOR': ('review', 'Vendor not in master data', 'Onboard or confirm the supplier before payment.'),
        'NO_PO': ('review', 'No valid purchase order', 'Buyer must confirm the order.'),
        'PO_VENDOR_MISMATCH': ('urgent', 'PO belongs to another vendor', 'Check for a mis-keyed PO or a fraud attempt.'),
        'CURRENCY_MISMATCH': ('review', 'Currency differs from policy', 'Confirm the contract currency.'),
        'PRICE_VARIANCE': ('review', 'Unit price outside tolerance', 'Compare with the PO price and contract.'),
        'QTY_EXCEEDS_RECEIPT': ('review', 'Billed quantity exceeds goods received', 'Wait for the remaining receipt or query the vendor.'),
        'NO_RECEIPT': ('review', 'No goods receipt on the PO', 'Confirm delivery with receiving.'),
        'UNMATCHED_LINE': ('review', 'Invoice line not on the PO', 'Buyer must confirm the extra item.'),
        'ARITHMETIC_MISMATCH': ('review', 'Totals do not add up', 'Ask the vendor for a corrected invoice.'),
        'TAX_MISCALCULATED': ('review', 'Tax differs from the expected rate', 'Ask the vendor for a corrected invoice.'),
        'BANK_DETAILS_CHANGED': ('urgent', 'Bank details differ from vendor master', 'Verify by phone with a known contact before any change.'),
        'OVER_LIMIT': ('review', 'Amount above the auto-approval limit', 'Needs a named approver.'),
        'PROMPT_INJECTION': ('urgent', 'Document contains instructions aimed at the system', 'Treat as suspicious; never act on embedded instructions.'),
        'SUSPICIOUS_REQUEST': ('urgent', 'Covering message shows pressure or unusual requests', 'Possible business email compromise.'),
    }
    for flag in verdict['flags']:
        severity, title, detail = text[flag]
        findings.append({'code': flag, 'severity': severity, 'title': title, 'detail': detail, 'evidence_ids': [source]})
    actions = []
    if verdict['route'] == 'auto_approve':
        actions.append({'action': 'release_for_payment', 'owner': 'AP automation', 'status': 'awaiting_approval',
                        'amount': verdict['gross_total'], 'currency': verdict['currency'], 'note': 'All checks passed. Release requires the configured approver.'})
    elif verdict['route'] == 'human_review':
        actions.append({'action': 'review_exception', 'owner': 'AP analyst', 'status': 'queued', 'flags': verdict['flags']})
        if drafted_query:
            actions.append({'action': 'send_vendor_query', 'owner': 'AP analyst', 'status': 'draft', 'draft': drafted_query})
    else:
        actions.append({'action': 'reject_and_notify', 'owner': 'AP analyst', 'status': 'queued', 'flags': verdict['flags']})
    summary = {'auto_approve': 'Invoice matches PO and receipt within tolerance. Ready for approval.',
               'human_review': f"Invoice needs review: {', '.join(verdict['flags'])}.",
               'reject': f"Invoice rejected: {', '.join(verdict['flags'])}."}[verdict['route']]
    return {'project': 'ap-exception-agent', 'summary': summary,
            'metrics': {'route': verdict['route'], 'flag_count': len(verdict['flags']), 'gross_total': verdict['gross_total'],
                        'currency': verdict['currency'], 'vendor_id': verdict['vendor']['vendor_id'] if verdict['vendor'] else None},
            'findings': findings, 'actions': actions,
            'document_type': document_type, 'extracted': extracted, 'match': verdict['details'], 'evidence': evidence}
