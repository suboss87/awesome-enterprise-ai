"""Read-only evidence checks. Amounts and quantities are never inferred by a model."""
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, localcontext

MAX_BYTES = 1_000_000
MAX_ROWS = 1000
NUM = re.compile(r'^(0|[1-9][0-9]{0,17})(\.[0-9]{1,6})?$')


class InvalidEvidence(ValueError):
    pass


def fail(message):
    raise InvalidEvidence(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def load_bytes(raw):
    if len(raw) > MAX_BYTES:
        fail('Input exceeds 1 MB limit')
    try:
        value = json.loads(raw, object_pairs_hook=unique_object,
                           parse_constant=lambda value: fail('Nonfinite JSON number'))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail('Invalid JSON: ' + str(exc))
    return value


def obj(value, required, optional=()):
    if not isinstance(value, dict):
        fail('Expected an object')
    missing = set(required) - value.keys()
    extra = value.keys() - set(required) - set(optional)
    if missing or extra:
        fail('Invalid fields; missing=' + str(sorted(missing)) + ', unsupported=' + str(sorted(extra)))
    return value


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 300:
        fail('Expected nonempty text of at most 300 characters')
    return value


def number(value):
    # Decimal strings make precision independent of the JSON parser or locale.
    if not isinstance(value, str) or not NUM.fullmatch(value):
        fail('Quantities/prices must be unsigned decimal strings (18 integer, 6 fraction digits maximum)')
    return Decimal(value)


def rows(value):
    if not isinstance(value, list) or len(value) > MAX_ROWS:
        fail('Expected at most 1000 records')
    return value


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(text(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            fail('Timestamps need a timezone')
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        fail('Invalid timestamp')


def fmt(value):
    return format(value, 'f')


def assess(data):
    with localcontext() as ctx:
        # Inputs <=24 digits; <=1000 sums/products require far fewer than 100.
        ctx.prec = 100
        return _assess(data)


def _assess(data):
    obj(data, ['schema_version', 'as_of', 'max_age_days', 'owners', 'purchase_order',
               'receipt_snapshot', 'prior_invoice_snapshot', 'invoice'])
    if type(data['schema_version']) is not int or data['schema_version'] != 1:
        fail('Unsupported schema version')
    now = timestamp(data['as_of'])
    age = data['max_age_days']
    if type(age) is not int or not 0 <= age <= 365:
        fail('max_age_days must be an integer from 0 to 365')
    owners = obj(data['owners'], [], ['accounts_payable', 'receiving', 'procurement'])
    for owner in owners.values():
        text(owner)
    findings = []

    def issue(code, role, message, refs, line=None):
        owner = owners.get(role)
        findings.append({'code': code, 'invoice_line_id': line, 'role': role,
                         'owner': owner or 'UNASSIGNED', 'message': message,
                         'source_refs': refs})
        if owner is None and code != 'OWNER_UNASSIGNED':
            findings.append({'code': 'OWNER_UNASSIGNED', 'invoice_line_id': line,
                             'role': role, 'owner': 'UNASSIGNED',
                             'message': 'Assign an accountable owner before resolving this exception.',
                             'source_refs': refs})

    def freshness(record, label):
        stamp = timestamp(record['observed_at'])
        if stamp > now:
            issue('FUTURE_EVIDENCE', 'accounts_payable', label + ' is dated after the evaluation time.', [record['source_ref']])
        elif (now - stamp).total_seconds() > age * 86400:
            issue('STALE_EVIDENCE', 'accounts_payable', label + ' exceeds the permitted evidence age.', [record['source_ref']])

    dimensions = ['entity', 'vendor', 'currency']
    header = ['id', 'source_ref', 'observed_at', 'entity', 'vendor', 'currency', 'lines']
    po = obj(data['purchase_order'], header)
    inv = obj(data['invoice'], header)
    for label, record in [('Purchase order', po), ('Current invoice', inv)]:
        for key in header:
            if key != 'lines':
                text(record[key])
        freshness(record, label)
    for dim in dimensions:
        if inv[dim] != po[dim]:
            issue('IDENTITY_MISMATCH', 'accounts_payable', 'Current invoice and PO disagree on ' + dim + '.', [inv['source_ref'], po['source_ref']])
    po_lines = {}
    for row in rows(po['lines']):
        obj(row, ['id', 'source_ref', 'uom', 'quantity', 'unit_price'])
        for key in ['id', 'source_ref', 'uom']:
            text(row[key])
        if row['id'] in po_lines:
            fail('Duplicate PO line ID')
        number(row['quantity']); number(row['unit_price'])
        po_lines[row['id']] = row
    if not po_lines:
        fail('PO requires lines')

    snapshots = []
    totals = [{}, {}]
    for idx, field in enumerate(['receipt_snapshot', 'prior_invoice_snapshot']):
        snap = obj(data[field], ['complete', 'source_ref', 'observed_at', 'records'])
        if type(snap['complete']) is not bool:
            fail('Snapshot completeness must be boolean')
        text(snap['source_ref']); freshness(snap, field)
        if not snap['complete']:
            issue('INCOMPLETE_EVIDENCE', 'receiving' if idx == 0 else 'accounts_payable',
                  field + ' is incomplete; the available balance is unknown.', [snap['source_ref']])
        seen = set()
        seen_refs = set()
        for row in rows(snap['records']):
            fields = ['id', 'source_ref', 'observed_at', 'po_line_id', 'entity', 'vendor', 'currency', 'uom']
            fields += ['received_quantity', 'accepted_quantity', 'rejected_quantity'] if idx == 0 else ['invoice_id', 'quantity', 'status']
            obj(row, fields)
            for key in fields:
                if 'quantity' not in key:
                    text(row[key])
            if row['id'] in seen or row['source_ref'] in seen_refs:
                fail('Duplicate snapshot record ID or source reference')
            seen_refs.add(row['source_ref'])
            seen.add(row['id']); freshness(row, field + ' record')
            key = row['po_line_id']
            if key not in po_lines:
                fail('Unknown PO line reference')
            if any(row[d] != po[d] for d in dimensions) or row['uom'] != po_lines[key]['uom']:
                fail('Snapshot entity/vendor/currency/UOM mismatch')
            if idx == 0:
                received = number(row['received_quantity'])
                accepted = number(row['accepted_quantity'])
                rejected = number(row['rejected_quantity'])
                if accepted + rejected != received:
                    fail('Accepted plus rejected must equal received quantity')
                qty = accepted
            else:
                if row['status'] != 'POSTED':
                    fail('Only prior POSTED invoice lines supported')
                if row['invoice_id'] == inv['id']:
                    fail('Current invoice must not appear in prior history')
                qty = number(row['quantity'])
            totals[idx][key] = totals[idx].get(key, Decimal(0)) + qty
        snapshots.append(snap)

    line_results = []
    seen = set()
    current_refs = set()
    current_totals = {}
    incompatible_groups = set()
    current_rows = rows(inv['lines'])
    if not current_rows:
        fail('Invoice requires lines')
    for row in current_rows:
        obj(row, ['id', 'source_ref', 'po_line_id', 'uom', 'quantity', 'unit_price'])
        for key in ['id', 'source_ref', 'po_line_id', 'uom']:
            text(row[key])
        if row['id'] in seen or row['source_ref'] in current_refs:
            fail('Duplicate current invoice line ID or source reference')
        current_refs.add(row['source_ref'])
        seen.add(row['id'])
        if row['po_line_id'] not in po_lines:
            fail('Current invoice references unknown PO line')
        qty = number(row['quantity']); number(row['unit_price'])
        key = row['po_line_id']
        if row['uom'] != po_lines[key]['uom']:
            incompatible_groups.add(key)
        current_totals[key] = current_totals.get(key, Decimal(0)) + qty
    for row in current_rows:
        key = row['po_line_id']; ordered = po_lines[key]
        refs = [r['source_ref'] for r in current_rows if r['po_line_id'] == key]
        refs.append(ordered['source_ref'])
        related = [r for s in snapshots for r in s['records'] if r['po_line_id'] == key]
        refs += [r['source_ref'] for r in related]
        refs += [s['source_ref'] for s in snapshots]
        qty = number(row['quantity']); price = number(row['unit_price'])
        accepted = totals[0].get(key, Decimal(0)); prior = totals[1].get(key, Decimal(0))
        compatible = all(inv[d] == po[d] for d in dimensions) and row['uom'] == ordered['uom']
        quantity_compatible = compatible and key not in incompatible_groups
        known = all(s['complete'] for s in snapshots) and quantity_compatible
        remaining = max(Decimal(0), accepted - prior)
        excess = max(Decimal(0), current_totals[key] - remaining)
        if row['uom'] != ordered['uom']:
            issue('UOM_MISMATCH', 'procurement', 'Invoice UOM differs from PO; no conversion inferred.', refs, row['id'])
        if compatible and price != number(ordered['unit_price']):
            delta = qty * (price - number(ordered['unit_price']))
            issue('PRICE_VARIANCE', 'procurement',
                  'Invoice unit price ' + fmt(price) + ' versus order ' + ordered['unit_price'] +
                  ' ' + inv['currency'] + '; line difference ' + fmt(delta) + ' ' + inv['currency'] +
                  '. Confirm the agreed price or provide a revised purchase order.', refs, row['id'])
        if known and key not in totals[0]:
            issue('MISSING_RECEIPT', 'receiving', 'No accepted receipt record supports this PO line. Obtain receiving evidence.', refs, row['id'])
        if known and prior > accepted:
            issue('PRIOR_OVERBILLING', 'accounts_payable', 'Prior posted quantity exceeds accepted receipts; reconcile history.', refs, row['id'])
        if known and excess > 0:
            issue('ACCEPTED_BALANCE_EXCEEDED', 'receiving',
                  'Current invoice total for this PO line exceeds accepted, unbilled receipts by ' + fmt(excess) + ' ' + ordered['uom'] + '. Confirm receipt or request invoice correction.', refs, row['id'])
        if quantity_compatible and current_totals[key] + prior > number(ordered['quantity']):
            issue('ORDER_QUANTITY_EXCEEDED', 'procurement', 'Cumulative billed quantity exceeds the purchase order.', refs, row['id'])
        line_results.append({'invoice_line_id': row['id'], 'po_line_id': key,
                             'accepted_quantity': fmt(accepted) if known else None,
                             'prior_billed_quantity': fmt(prior) if known else None,
                             'remaining_accepted_quantity': fmt(remaining) if known else None,
                             'current_po_line_quantity': fmt(current_totals[key]) if quantity_compatible else None,
                             'excess_quantity': fmt(excess) if known else None,
                             'line_amount': fmt(qty * price) if compatible else None, 'currency': inv['currency'],
                             'invoice_unit_price': fmt(price) if compatible else None,
                             'po_unit_price': fmt(number(ordered['unit_price'])) if compatible else None,
                             'unit_price_delta': fmt(price - number(ordered['unit_price'])) if compatible else None,
                             'line_price_delta': fmt(qty * (price - number(ordered['unit_price']))) if compatible else None,
                             'source_refs': refs})
    if not owners.get('accounts_payable'):
        issue('OWNER_UNASSIGNED', 'accounts_payable', 'Assign an accounts-payable reviewer.', [inv['source_ref']])
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    return {'schema_version': 1, 'invoice_id': inv['id'], 'as_of': data['as_of'],
            'input_sha256': digest, 'verdict': 'REVIEW_REQUIRED' if findings else 'NO_EXCEPTIONS_IN_SUPPLIED_EVIDENCE',
            'limitations': 'Read-only evidence review. This is never payment approval. Completeness is an exporter assertion, not independently proven.',
            'lines': line_results, 'exceptions': findings}
