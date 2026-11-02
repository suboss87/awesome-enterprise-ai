"""Rules-only baseline in the style of per-customer PO templates.

Two layouts have hand-written templates (the tabular PO and the key-value PO, as a desk would map
for its two biggest customers). Any other layout falls back to generic header regexes and finds no
lines, so those orders go to the desk. A keyword gate catches documents titled as RFQs or
acknowledgements. Embedded instructions are invisible to it. The reading then goes through the same
`ordering.py` rules as the agent, so the comparison isolates the reading step.
"""
import importlib.util
import re
from pathlib import Path

_here = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('order_entry_rules_b', _here/'ordering.py')
ordering = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ordering)
_aspec = importlib.util.spec_from_file_location('order_entry_agent_b', _here/'agent.py')
agent_module = importlib.util.module_from_spec(_aspec)
_aspec.loader.exec_module(agent_module)

NOT_AN_ORDER = re.compile(r'request for quotation|\bRFQ\b|order acknowledg', re.I)
MONEY = r'([\d,]+\.\d{2})'


def _first(pattern, text, default=''):
    m = re.search(pattern, text, re.I | re.M)
    return m.group(1).strip() if m else default


def _num(raw):
    return float(raw.replace(',', '')) if raw else 0.0


def extract(text):
    """Return the recording {header, lines} that the templates can read."""
    lines = []
    if re.search(r'^Ln\s+Item No\s+Description', text, re.M):             # template 1: tabular PO
        header = {'customer_name': _first(r'^Buyer:\s*(.+)$', text), 'customer_account': _first(r'^Account No:\s*(\S+)', text),
                  'customer_po_number': _first(r'^PO Number:\s*(\S+)', text), 'requested_ship_date': _first(r'^Requested Ship Date:\s*(\d{4}-\d{2}-\d{2})', text),
                  'ship_to': _first(r'^Ship To:\s*(.+)$', text), 'po_total': _num(_first(r'^PO Total:\s*' + MONEY, text))}
        for m in re.finditer(r'^(\d+)\s+(\S+)\s+(.+?)\s+(\d+)\s+(EA|CS)\s+' + MONEY + r'\s+' + MONEY + r'$', text, re.M):
            n, code, _desc, qty, uom, price, _ext = m.groups()
            lines.append({'line': int(n), 'customer_part': '' if code == '-' else code, 'sku': '', 'qty': int(qty), 'uom': uom,
                          'unit_price_on_po': _num(price), 'quote': m.group(0)})
    elif re.search(r'^Line 1: ', text, re.M):                              # template 2: key-value PO
        header = {'customer_name': text.strip().splitlines()[0].strip(), 'customer_account': _first(r'^Customer account:\s*(\S+)', text),
                  'customer_po_number': _first(r'^Order reference:\s*(\S+)', text), 'requested_ship_date': _first(r'^Need by:\s*(\d{4}-\d{2}-\d{2})', text),
                  'ship_to': _first(r'^Deliver to:\s*(.+)$', text), 'po_total': _num(_first(r'^Order value:\s*USD\s*' + MONEY, text))}
        for m in re.finditer(r'^Line (\d+): (?:(\S+) \| )?(.+?) \| qty (\d+) (EA|CS) \| ' + MONEY + r' per \w+$', text, re.M):
            n, code, _desc, qty, uom, price = m.groups()
            lines.append({'line': int(n), 'customer_part': code or '', 'sku': '', 'qty': int(qty), 'uom': uom,
                          'unit_price_on_po': _num(price), 'quote': m.group(0)})
    else:                                                                  # generic fallback: header only
        header = {'customer_name': text.strip().splitlines()[0].strip(), 'customer_account': '',
                  'customer_po_number': _first(r'\b(?:PO|Purchase Order|Order)\s*(?:No\.?|Number|#)?\s*[:#]?\s*([A-Z0-9][A-Z0-9-]{3,})', text),
                  'requested_ship_date': '', 'ship_to': '', 'po_total': 0.0}
    return {'header': header, 'lines': lines}


def run(data):
    document, _erp, _policy = agent_module.validate(data)
    doc_type = 'rfq' if NOT_AN_ORDER.search(document['text']) else 'purchase_order'
    recording = extract(document['text']) if doc_type == 'purchase_order' else None
    if recording is not None and not recording['lines']:
        recording = None                                                   # nothing read: the rules see no recorded lines
    verdict = ordering.assess(data, doc_type, recording)
    output = ordering.build_output(data, verdict, doc_type, None, [])
    output['baseline'] = 'regex-templates'
    return output
