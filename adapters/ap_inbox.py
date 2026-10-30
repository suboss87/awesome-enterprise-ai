"""AP inbox adapter: turn a vendor email and an ERP export into an AP Exception Agent input.

Standard library only. Two entry points share one parse path:

    invoice_from_eml(path)            one .eml file (local drop folder, or saved from any mail client)
    fetch_imap(host, user, password)  unread messages from an IMAP folder, as .eml bytes

ERP data comes from four CSV exports (vendors, purchase_orders, goods_receipts, ap_ledger) that every
ERP can produce; `erp_from_csv(folder)` builds the records the agent expects. Replace that function with
an API client when you connect a real ERP; the agent input does not change.

PDF attachments are converted with `pdftotext` (poppler) when it is installed. Without it the adapter
records the attachment as needing OCR and uses the email body as the document, so nothing is silently
skipped. Images are always recorded as needing OCR.

Usage:
    python3 -m adapters.ap_inbox --eml inbox/invoice.eml --erp exports/ --policy policy.json --out case.json
    python3 -m enterprise_ai run ap-exception-agent --input case.json
"""
import argparse
import csv
import email
import email.policy
import html
import imaplib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

TEXT_TYPES = {'text/plain', 'text/csv', 'text/html'}
OCR_TYPES = {'image/png', 'image/jpeg', 'image/tiff', 'application/pdf'}


def _strip_html(markup):
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', markup, flags=re.S | re.I)
    text = re.sub(r'<br\s*/?>|</p>|</div>|</tr>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    return re.sub(r'[ \t]+', ' ', re.sub(r'\n\s*\n+', '\n\n', text)).strip()


def _pdf_text(payload):
    tool = shutil.which('pdftotext')
    if not tool:
        return None
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as handle:
        handle.write(payload)
        path = handle.name
    try:
        result = subprocess.run([tool, '-layout', path, '-'], capture_output=True, timeout=60, check=False)
        return result.stdout.decode('utf-8', 'replace').strip() if result.returncode == 0 else None
    finally:
        os.unlink(path)


def invoice_from_message(message, doc_id=None):
    """Build the `invoice` block from an email.message.EmailMessage."""
    body_part = message.get_body(preferencelist=('plain', 'html'))
    body = ''
    if body_part is not None:
        content = body_part.get_content()
        body = _strip_html(content) if body_part.get_content_type() == 'text/html' else content.strip()
    documents, needs_ocr = [], []
    for part in message.iter_attachments():
        ctype = part.get_content_type()
        name = part.get_filename() or f'attachment.{ctype.split("/")[-1]}'
        if ctype in TEXT_TYPES:
            content = part.get_content()
            if isinstance(content, bytes):
                content = content.decode(part.get_content_charset() or 'utf-8', 'replace')
            documents.append((name, _strip_html(content) if ctype == 'text/html' else content.strip()))
        elif ctype == 'application/pdf':
            text = _pdf_text(part.get_payload(decode=True))
            (documents if text else needs_ocr).append((name, text) if text else name)
        elif ctype in OCR_TYPES:
            needs_ocr.append(name)
    message_id = (message.get('Message-ID') or '').strip('<> ')
    invoice = {'id': doc_id or (message_id or f'eml-{abs(hash(body)) % 10**8:08d}'), 'channel': 'email'}
    if documents:
        invoice['text'] = '\n\n'.join(f'--- {name} ---\n{text}' if len(documents) > 1 else text for name, text in documents)
        if body:
            invoice['email_body'] = body
    else:
        invoice['text'] = body
    meta = {'from': message.get('From', ''), 'subject': message.get('Subject', ''), 'date': message.get('Date', ''),
            'attachments_used': [name for name, _ in documents], 'attachments_need_ocr': needs_ocr}
    return invoice, meta


def invoice_from_eml(path, doc_id=None):
    with open(path, 'rb') as handle:
        message = email.message_from_binary_file(handle, policy=email.policy.default)
    return invoice_from_message(message, doc_id or Path(path).stem)


def fetch_imap(host, user, password, folder='INBOX', unseen_only=True, limit=50, port=993):
    """Yield (uid, EmailMessage) for messages in the folder. Read-only: nothing is flagged or moved."""
    client = imaplib.IMAP4_SSL(host, port)
    try:
        client.login(user, password)
        client.select(folder, readonly=True)
        status, data = client.uid('search', None, 'UNSEEN' if unseen_only else 'ALL')
        if status != 'OK':
            raise RuntimeError(f'IMAP search failed: {status}')
        for uid in data[0].split()[-limit:]:
            status, parts = client.uid('fetch', uid, '(BODY.PEEK[])')
            if status == 'OK' and parts and isinstance(parts[0], tuple):
                yield uid.decode(), email.message_from_bytes(parts[0][1], policy=email.policy.default)
    finally:
        try:
            client.logout()
        except (imaplib.IMAP4.error, OSError):
            pass


def _rows(folder, name):
    path = Path(folder) / f'{name}.csv'
    if not path.exists():
        raise FileNotFoundError(f'{path} is required (export it from the ERP)')
    with open(path, newline='', encoding='utf-8-sig') as handle:
        return list(csv.DictReader(handle))


def _num(value, kind=float):
    value = (value or '').strip().replace(',', '')
    return kind(value) if value else kind(0)


def erp_from_csv(folder):
    """Four flat exports -> the nested records the agent reads. One row per PO line and per receipt line."""
    vendors = [{'vendor_id': r['vendor_id'], 'name': r['name'], 'tax_id': r.get('tax_id', ''), 'bank_iban': r.get('bank_iban', ''),
                'payment_terms_days': _num(r.get('payment_terms_days'), int)} for r in _rows(folder, 'vendors')]
    pos = {}
    for r in _rows(folder, 'purchase_orders'):
        po = pos.setdefault(r['po_number'], {'po_number': r['po_number'], 'vendor_id': r['vendor_id'], 'currency': r.get('currency', 'USD'),
                                             'ordered_on': r.get('ordered_on', ''), 'lines': []})
        po['lines'].append({'line': _num(r['line'], int), 'sku': r.get('sku', ''), 'description': r.get('description', ''),
                            'qty_ordered': _num(r['qty_ordered']), 'unit_price': _num(r['unit_price'])})
    grns = {}
    for r in _rows(folder, 'goods_receipts'):
        grn = grns.setdefault(r['grn'], {'grn': r['grn'], 'po_number': r['po_number'], 'received_on': r.get('received_on', ''), 'lines': []})
        grn['lines'].append({'po_line': _num(r['po_line'], int), 'qty_accepted': _num(r['qty_accepted']), 'qty_rejected': _num(r.get('qty_rejected'))})
    ledger = [{'invoice_number': r['invoice_number'], 'vendor_id': r['vendor_id'], 'gross_total': _num(r['gross_total']),
               'invoice_date': r.get('invoice_date', ''), 'status': r.get('status', 'posted')} for r in _rows(folder, 'ap_ledger')]
    return {'vendors': vendors, 'purchase_orders': list(pos.values()), 'goods_receipts': list(grns.values()), 'ap_ledger': ledger}


def build_input(invoice, erp, policy, as_of=None):
    return {'as_of': as_of or date.today().isoformat(), 'invoice': invoice, 'erp': erp, 'policy': policy}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Build an AP Exception Agent input from an email and ERP CSV exports')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--eml', help='Path to one .eml file')
    source.add_argument('--imap', metavar='HOST', help='Fetch unread messages from an IMAP host (password in AP_INBOX_PASSWORD)')
    parser.add_argument('--user', help='IMAP user')
    parser.add_argument('--folder', default='INBOX')
    parser.add_argument('--erp', required=True, help='Folder with vendors.csv, purchase_orders.csv, goods_receipts.csv, ap_ledger.csv')
    parser.add_argument('--policy', required=True, help='JSON file with currency, tolerances, auto_approve_limit, tax_rate_pct')
    parser.add_argument('--as-of', default=None)
    parser.add_argument('--doc-id', help='Document id for the case (default: the .eml file name)')
    parser.add_argument('--out', help='Write the case JSON here (default: stdout). With --imap, a folder; one file per message')
    args = parser.parse_args(argv)
    erp = erp_from_csv(args.erp)
    policy = json.load(open(args.policy))
    if args.eml:
        invoice, meta = invoice_from_eml(args.eml, args.doc_id)
        case = build_input(invoice, erp, policy, args.as_of)
        text = json.dumps(case, indent=2, ensure_ascii=False)
        if args.out:
            Path(args.out).write_text(text)
            Path(args.out).with_suffix('.meta.json').write_text(json.dumps(meta, indent=2, ensure_ascii=False))
            print(f'wrote {args.out} (+ .meta.json); attachments needing OCR: {meta["attachments_need_ocr"] or "none"}', file=sys.stderr)
        else:
            print(text)
        return 0
    password = os.environ.get('AP_INBOX_PASSWORD')
    if not (args.user and password):
        print('IMAP needs --user and AP_INBOX_PASSWORD in the environment', file=sys.stderr)
        return 2
    out = Path(args.out or 'inbox-cases')
    out.mkdir(parents=True, exist_ok=True)
    count = 0
    for uid, message in fetch_imap(args.imap, args.user, password, args.folder):
        invoice, meta = invoice_from_message(message, f'imap-{uid}')
        case = build_input(invoice, erp, policy, args.as_of)
        (out / f'{invoice["id"]}.json').write_text(json.dumps(case, indent=2, ensure_ascii=False))
        (out / f'{invoice["id"]}.meta.json').write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        count += 1
    print(f'wrote {count} case files to {out}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
