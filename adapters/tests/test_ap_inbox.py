import json
import unittest
from pathlib import Path

from adapters.ap_inbox import erp_from_csv, invoice_from_eml, build_input
from enterprise_ai.runner import execute, example_replay

ROOT = Path(__file__).resolve().parents[2]
FX = ROOT / 'adapters/fixtures/ap'
EXAMPLE = json.loads((ROOT / 'projects/ap-exception-agent/examples/input.json').read_text())


class APInboxAdapter(unittest.TestCase):
    def test_eml_yields_the_attachment_as_document_and_the_body_as_covering_email(self):
        invoice, meta = invoice_from_eml(FX / 'INV-2265.eml')
        self.assertEqual(invoice['text'], EXAMPLE['invoice']['text'])
        self.assertIn('INV-2265', invoice['email_body'])
        self.assertEqual(invoice['channel'], 'email')
        self.assertEqual(meta['attachments_used'], ['INV-2265.txt'])
        self.assertEqual(meta['attachments_need_ocr'], [])

    def test_csv_exports_rebuild_the_erp_records_exactly(self):
        erp = erp_from_csv(FX)
        for key in ('vendors', 'purchase_orders', 'goods_receipts', 'ap_ledger'):
            self.assertEqual(erp[key], EXAMPLE['erp'][key], key)

    def test_missing_export_is_a_clear_error(self):
        with self.assertRaises(FileNotFoundError):
            erp_from_csv(ROOT / 'adapters/tests')

    def test_built_case_runs_through_the_agent_on_the_recorded_replay(self):
        invoice, _ = invoice_from_eml(FX / 'INV-2265.eml', doc_id=EXAMPLE['invoice']['id'])
        case = build_input(invoice, erp_from_csv(FX), json.loads((FX / 'policy.json').read_text()), EXAMPLE['as_of'])
        out = execute('ap-exception-agent', case, 'replay', replay=example_replay('ap-exception-agent'))
        self.assertIn(out['metrics']['route'], ('auto_approve', 'human_review', 'reject'))
        self.assertTrue(out['findings'] or out['metrics']['route'] == 'auto_approve')


if __name__ == '__main__':
    unittest.main()
