"""Self-contained, escaped HTML review brief. No scripts or remote assets."""
from html import escape


def render_html(report):
    def esc(value):
        return escape(str(value), quote=True)
    def refs(values):
        return '<ul class="refs">' + ''.join('<li>' + esc(v) + '</li>' for v in values) + '</ul>'
    cards = ''.join('<article><p class="eyebrow">' + esc(e['code'].replace('_', ' ')) +
                    '</p><h2>' + esc(e['message']) + '</h2><p>Owner: <strong>' + esc(e['owner']) +
                    '</strong> · Role: ' + esc(e['role']) + '</p>' + refs(e['source_refs']) + '</article>'
                    for e in report['exceptions'])
    lines = ''.join('<tr>' + ''.join('<td>' + esc(row.get(k) if row.get(k) is not None else 'Unknown') + '</td>'
                                   for k in ['invoice_line_id', 'accepted_quantity', 'prior_billed_quantity', 'remaining_accepted_quantity', 'current_po_line_quantity', 'excess_quantity']) + '</tr>'
                    for row in report['lines'])
    status = 'Review required' if report['exceptions'] else 'No exceptions in supplied evidence'
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>Invoice exception brief</title><style>
:root{font-family:system-ui,sans-serif;color:#172b35;background:#f3f5f4}body{margin:0}main{max-width:1000px;margin:auto;padding:40px 22px 64px}header{border-top:6px solid #17665d;padding-top:24px;margin-bottom:32px}.eyebrow{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#386057;font-weight:700}h1{font-size:clamp(30px,6vw,48px);line-height:1.1;margin:12px 0}h2{font-size:20px;line-height:1.4}p{line-height:1.6}.status{display:inline-block;padding:8px 12px;background:#fff1cb;color:#493300;border-radius:5px;font-weight:700}article{background:white;border:1px solid #cbd7d3;border-left:4px solid #947018;padding:18px 22px;margin:18px 0;border-radius:4px}.refs{font:12px/1.6 ui-monospace,monospace;overflow-wrap:anywhere;color:#405650;padding-left:18px}.table{overflow:auto;background:#fff;border:1px solid #cbd7d3}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:14px;border-bottom:1px solid #dce3df}th{background:#e7efeb}footer{margin-top:28px;font-size:13px;color:#405650;overflow-wrap:anywhere}code{font-size:12px}@media(max-width:600px){main{padding:24px 14px}article{padding:14px}th,td{padding:10px}}</style></head><body><main><header><p class="eyebrow">Procurement operations · Read-only review</p><h1>Invoice exception brief</h1><p>Invoice <strong>''' + esc(report['invoice_id']) + '</strong> · As of ' + esc(report['as_of']) + '</p><p class="status">' + esc(status) + '</p></header><section aria-label="Receipt balances"><h2>What the supplied records support</h2><p>Quantities are grouped by purchase-order line. Repeated line totals must not be added together.</p><div class="table"><table><thead><tr><th>Invoice line</th><th>Accepted</th><th>Previously billed</th><th>Available</th><th>Current total</th><th>Excess</th></tr></thead><tbody>' + lines + '</tbody></table></div></section><section aria-label="Follow-up actions"><h2>Follow-up actions</h2>' + (cards or '<p>No discrepancies were found by these checks. This does not authorize payment.</p>') + '</section><footer><p>' + esc(report['limitations']) + '</p><p>Evidence digest: <code>' + esc(report['input_sha256']) + '</code></p><p>Amounts exclude unsupported taxes, discounts, returns and currency conversions.</p></footer></main></body></html>'
