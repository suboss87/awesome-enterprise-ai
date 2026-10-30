"""Rules-only baseline in the style of template-based invoice tools.

Two layouts have hand-written templates (the tabular and the key-value layout,
as a team would write for its two biggest suppliers). Any other layout falls back
to generic regexes. The extraction then goes through the same `matching.py` rules
as the agent, so the comparison isolates the reading step.
"""
import importlib.util
import re
from pathlib import Path

_here = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('ap_matching_b', _here/'matching.py')
matching = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(matching)
_aspec = importlib.util.spec_from_file_location('ap_agent_b', _here/'agent.py')
agent_module = importlib.util.module_from_spec(_aspec)
_aspec.loader.exec_module(agent_module)

NUM = r'-?[\d.,]+'


def _num(raw):
    raw = raw.strip().replace(' ', '')
    if re.fullmatch(r'-?\d{1,3}(\.\d{3})*,\d{1,2}', raw) or re.fullmatch(r'-?\d+,\d{1,2}', raw):
        raw = raw.replace('.', '').replace(',', '.')
    else:
        raw = raw.replace(',', '')
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _first(pattern, text, default=''):
    m = re.search(pattern, text, re.I | re.M)
    return m.group(1).strip() if m else default


def _common(text):
    doc_type = 'invoice'
    if re.search(r'\bcredit\s+note\b', text, re.I):
        doc_type = 'credit_note'
    elif re.search(r'\bdelivery\s+note\b', text, re.I) and not re.search(r'\binvoice\b', text, re.I):
        doc_type = 'delivery_note'
    number = _first(r'Invoice\s*(?:No\.?|Number|#)?\s*[:#]?\s*([A-Z]{1,4}-\d{3,})', text)
    date = _first(r'Date\s*:?\s*(\d{4}-\d{2}-\d{2})', text)
    if not date:
        m = re.search(r'Date\s*:?\s*(\d{2})\.(\d{2})\.(\d{4})', text, re.I)
        date = f'{m.group(3)}-{m.group(2)}-{m.group(1)}' if m else ''
    pos = list(dict.fromkeys(re.findall(r'\b(PO-\d{5})\b', text)))
    currency = _first(r'\b(USD|EUR|GBP)\b', text, 'USD')
    iban = _first(r'IBAN:?\s*([A-Z]{2}\d{2}[A-Z0-9]{10,30})', text)
    return doc_type, number, date, pos, currency, iban


def extract(text):
    doc_type, number, date, pos, currency, iban = _common(text)
    single_po = pos[0] if len(pos) == 1 else ''
    lines = []
    if 'SKU       Description' in text:                      # template 1: tabular layout
        vendor = _first(r'^From:\s*(.+)$', text)
        tax_id = _first(r'^VAT No:\s*(.+)$', text)
        for m in re.finditer(r'^(\S+)\s+(.+?)\s{2,}(' + NUM + r')\s{2,}(' + NUM + r')\s{2,}(' + NUM + r')\s*$', text, re.M):
            sku, desc, qty, price, total = m.groups()
            if sku.upper() in ('SKU', 'SUBTOTAL', 'VAT', 'TOTAL'):
                continue
            lines.append({'po_number': single_po, 'sku': sku, 'description': desc.strip(), 'qty': _num(qty), 'unit_price': _num(price), 'line_total': _num(total)})
        subtotal = _num(_first(r'^Subtotal\s+(' + NUM + ')', text, '0'))
        tax = _num(_first(r'^VAT \(20%\)\s+(' + NUM + ')', text, '0'))
        gross = _num(_first(r'^Total due\s+(' + NUM + ')', text, '0'))
    elif re.search(r'^Items:$', text, re.M):                 # template 2: key-value layout
        vendor = text.strip().splitlines()[0].strip()
        tax_id = _first(r'^Tax ID:\s*(.+)$', text)
        for m in re.finditer(r'^- (.+?) \(([A-Z]+-\d+)\) x(' + NUM + r') @ (' + NUM + r') = (' + NUM + r')(?: \[PO (PO-\d{5})\])?\s*$', text, re.M):
            desc, sku, qty, price, total, line_po = m.groups()
            lines.append({'po_number': line_po or single_po, 'sku': sku, 'description': desc, 'qty': _num(qty), 'unit_price': _num(price), 'line_total': _num(total)})
        subtotal = _num(_first(r'^Subtotal:\s*(' + NUM + ')', text, '0'))
        tax = _num(_first(r'^Tax 20%:\s*(' + NUM + ')', text, '0'))
        gross = _num(_first(r'^Amount due:\s*[A-Z]{3}\s*(' + NUM + ')', text, '0'))
    else:                                                     # generic fallback for unknown layouts
        vendor = _first(r'^(?:From|Supplier|Vendor)\s*:\s*(.+)$', text) or text.strip().splitlines()[0].strip()
        tax_id = _first(r'(?:VAT|Tax|USt)[-\s]*(?:No|ID|IdNr)[.:\s]*([A-Z0-9-]{6,})', text)
        subtotal = _num(_first(r'(?:Subtotal|Net)\s*(?:is|:)?\s*(' + NUM + ')', text, '0'))
        tax = _num(_first(r'(?:VAT|tax)(?:\s*(?:at|\()?\s*\d+%\)?)?\s*(?:is|:)?\s*(' + NUM + ')', text, '0'))
        gross = _num(_first(r'(?:Total|Amount)\b[^\n\d-]{0,40}?(' + NUM + ')', text, '0'))
    return doc_type, {'vendor_name': vendor, 'vendor_tax_id': tax_id, 'invoice_number': number, 'invoice_date': date,
                      'po_numbers': pos, 'currency': currency, 'lines': lines, 'subtotal': subtotal, 'tax_total': tax,
                      'gross_total': gross, 'bank_iban': iban}


def run(data):
    invoice, erp, policy = agent_module.validate(data)
    doc_type, extracted = extract(invoice['text'])
    if not extracted['bank_iban'] and invoice.get('email_body'):
        extracted['bank_iban'] = _first(r'IBAN:?\s*([A-Z]{2}\d{2}[A-Z0-9]{10,30})', invoice['email_body'])
    verdict = matching.match(extracted, erp, policy, doc_type)
    output = matching.build_output(extracted, verdict, doc_type, None, [], invoice['id'])
    output['baseline'] = 'regex-templates'
    return output
