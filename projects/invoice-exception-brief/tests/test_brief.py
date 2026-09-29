import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from invoice_exception_brief import InvalidEvidence, assess, load_bytes
from invoice_exception_brief.render import render_html

ROOT = Path(__file__).resolve().parents[1]


def fixture(name='clean'):
    return load_bytes((ROOT / 'examples' / (name + '.json')).read_bytes())


class BriefTests(unittest.TestCase):
    def test_mixed_sibling_units_have_no_invented_aggregate(self):
        data = fixture()
        data['invoice']['lines'].append(dict(data['invoice']['lines'][0],
            id='I-BOX', source_ref='ap:invoice/100/box', uom='BOX', quantity='1'))
        for reverse in (False, True):
            if reverse:
                data['invoice']['lines'].reverse()
            report = assess(data)
            self.assertEqual(report['verdict'], 'REVIEW_REQUIRED')
            for line in report['lines']:
                self.assertIsNone(line['current_po_line_quantity'])
                self.assertIsNone(line['excess_quantity'])
                self.assertIn('ap:invoice/100/box', line['source_refs'])
                self.assertIn('ap:invoice/100/1', line['source_refs'])
            codes = {item['code'] for item in report['exceptions']}
            self.assertIn('UOM_MISMATCH', codes)
            self.assertFalse({'ACCEPTED_BALANCE_EXCEEDED', 'ORDER_QUANTITY_EXCEEDED'} & codes)

    def test_timestamp_conversion_overflow_is_invalid_evidence(self):
        data = fixture()
        data['receipt_snapshot']['observed_at'] = '0001-01-01T00:00:00+23:59'
        with self.assertRaises(InvalidEvidence):
            assess(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'overflow.json'
            path.write_text(json.dumps(data))
            result = subprocess.run([sys.executable, '-m', 'invoice_exception_brief', str(path)],
                                    cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertNotIn('Traceback', result.stderr)

    def test_clean_and_no_mutation(self):
        d = fixture(); before = copy.deepcopy(d)
        r = assess(d)
        self.assertEqual(r['verdict'], 'NO_EXCEPTIONS_IN_SUPPLIED_EVIDENCE')
        self.assertEqual(r['lines'][0]['line_amount'], '250.00')
        self.assertEqual(d, before)

    def test_accepted_not_shipped(self):
        r = assess(fixture('partial_receipt'))
        self.assertEqual(r['lines'][0]['excess_quantity'], '3')
        self.assertIn('ACCEPTED_BALANCE_EXCEEDED', [e['code'] for e in r['exceptions']])

    def test_prior_posted_consumes_receipt(self):
        r = assess(fixture('prior_consumption'))
        self.assertEqual(r['lines'][0]['remaining_accepted_quantity'], '2')
        self.assertEqual(r['lines'][0]['excess_quantity'], '6')
        self.assertIn('ap:invoice/99/1', r['lines'][0]['source_refs'])

    def test_unknown_history_never_zero(self):
        d=fixture();d['prior_invoice_snapshot']['complete']=False
        r=assess(d)
        self.assertIsNone(r['lines'][0]['prior_billed_quantity'])
        self.assertEqual(r['verdict'],'REVIEW_REQUIRED')

    def test_missing_receipt_and_owner(self):
        d=fixture();d['receipt_snapshot']['records']=[];d['owners']={}
        codes={e['code'] for e in assess(d)['exceptions']}
        self.assertTrue({'MISSING_RECEIPT','OWNER_UNASSIGNED'} <= codes)

    def test_split_current_lines_do_not_reuse_receipt(self):
        d=fixture('prior_consumption');d['prior_invoice_snapshot']['records']=[]
        d['invoice']['lines'].append(dict(d['invoice']['lines'][0],id='I-2',source_ref='ap:invoice/100/2'))
        r=assess(d)
        self.assertEqual([l['excess_quantity'] for l in r['lines']],['6','6'])
        for line in r['lines']:
            self.assertTrue({'ap:invoice/100/1', 'ap:invoice/100/2'} <= set(line['source_refs']))
        d['invoice']['lines'].reverse()
        self.assertEqual({l['invoice_line_id']:l['excess_quantity'] for l in assess(d)['lines']}, {'I-1':'6','I-2':'6'})

    def test_po_lines_not_pooled(self):
        d=fixture();d['purchase_order']['lines'].append(dict(d['purchase_order']['lines'][0],id='P-2',source_ref='po:2'))
        d['receipt_snapshot']['records'][0]['po_line_id']='P-2'
        r=assess(d)
        self.assertEqual(r['lines'][0]['accepted_quantity'],'0')
        self.assertEqual(r['verdict'],'REVIEW_REQUIRED')

    def test_exact_fractional_quantities(self):
        d=fixture();d['invoice']['lines'][0].update(quantity='0.3',unit_price='0.10');d['purchase_order']['lines'][0].update(quantity='0.3',unit_price='0.10')
        d['receipt_snapshot']['records'][0].update(received_quantity='0.1',accepted_quantity='0.1')
        d['receipt_snapshot']['records'].append(dict(d['receipt_snapshot']['records'][0],id='R-2',source_ref='wms:2',received_quantity='0.2',accepted_quantity='0.2'))
        r=assess(d)
        self.assertEqual(r['verdict'],'NO_EXCEPTIONS_IN_SUPPLIED_EVIDENCE')
        self.assertEqual(r['lines'][0]['line_amount'],'0.030')

    def test_invalid_numbers(self):
        for value in [True,False,0,0.1,'-1','NaN','Infinity','1e999999','0.0000001','9999999999999999999']:
            with self.subTest(value=value):
                d=fixture();d['invoice']['lines'][0]['quantity']=value
                with self.assertRaises(InvalidEvidence):assess(d)

    def test_duplicate_keys_ids_and_current_in_history(self):
        with self.assertRaises(InvalidEvidence):load_bytes(b'{"x":1,"x":2}')
        for collection in [('purchase_order','lines'),('invoice','lines'),('receipt_snapshot','records')]:
            d=fixture();d[collection[0]][collection[1]].append(copy.deepcopy(d[collection[0]][collection[1]][0]))
            with self.assertRaises(InvalidEvidence):assess(d)
        d=fixture('prior_consumption');d['prior_invoice_snapshot']['records'][0]['invoice_id']=d['invoice']['id']
        with self.assertRaises(InvalidEvidence):assess(d)

    def test_snapshot_identity_mismatch(self):
        for key in ['entity','vendor','currency','uom']:
            d=fixture();d['receipt_snapshot']['records'][0][key]='wrong'
            with self.assertRaises(InvalidEvidence):assess(d)

    def test_current_identity_mismatch_held(self):
        for key in ['entity','vendor','currency']:
            d=fixture();d['invoice'][key]='wrong'
            self.assertEqual(assess(d)['verdict'],'REVIEW_REQUIRED')
        d=fixture();d['invoice']['lines'][0]['uom']='BOX'
        self.assertEqual(assess(d)['verdict'],'REVIEW_REQUIRED')

    def test_stale_and_future(self):
        for stamp,code in [('2026-01-01T00:00:00Z','STALE_EVIDENCE'),('2027-01-01T00:00:00Z','FUTURE_EVIDENCE')]:
            d=fixture();d['receipt_snapshot']['observed_at']=stamp
            self.assertIn(code,[e['code'] for e in assess(d)['exceptions']])
        d=fixture();d['as_of']='2026-09-29T09:00:00'
        with self.assertRaises(InvalidEvidence):assess(d)

    def test_unsupported_features_fail_closed(self):
        for key in ['tax','discount','return_quantity','fx_rate']:
            d=fixture();d['invoice'][key]='1'
            with self.assertRaises(InvalidEvidence):assess(d)
        d=fixture();d['receipt_snapshot']['records'][0]['rejected_quantity']='1'
        with self.assertRaises(InvalidEvidence):assess(d)

    def test_digest_changes_and_html_escapes(self):
        d=fixture();first=assess(d)['input_sha256']
        d['invoice']['id']='<script>alert(1)</script>'
        r=assess(d);html=render_html(r)
        self.assertNotEqual(first,r['input_sha256'])
        self.assertNotIn('<script>',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertNotIn('https://',html)
        self.assertIn('viewport',html)

    def test_cli_exit_codes_and_files_unchanged(self):
        for name,code in [('clean',0),('partial_receipt',1),('missing_evidence',1),('prior_consumption',1)]:
            path=ROOT/'examples'/(name+'.json');before=path.read_bytes()
            p=subprocess.run([sys.executable,'-m','invoice_exception_brief',str(path)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(p.returncode,code,p.stderr)
            self.assertEqual(path.read_bytes(),before)
            self.assertIn('input_sha256',json.loads(p.stdout))
        p=subprocess.run([sys.executable,'-m','invoice_exception_brief','missing-file'],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(p.returncode,2)

    def test_duplicate_source_alias_rejected(self):
        d=fixture()
        d['receipt_snapshot']['records'].append(dict(d['receipt_snapshot']['records'][0],id='R-alias'))
        with self.assertRaises(InvalidEvidence):assess(d)

    def test_price_delta_and_incompatible_figures(self):
        d=fixture();d['invoice']['lines'][0]['unit_price']='13.25'
        line=assess(d)['lines'][0]
        self.assertEqual(line['unit_price_delta'],'0.75')
        self.assertEqual(line['line_price_delta'],'15.00')
        self.assertIn('15.00 GBP', render_html(assess(d)))
        d['invoice']['currency']='USD'
        line=assess(d)['lines'][0]
        self.assertIsNone(line['line_amount'])
        self.assertIsNone(line['excess_quantity'])

    def test_bounded_input(self):
        with self.assertRaises(InvalidEvidence):load_bytes(b' ' * 1_000_001)
        with self.assertRaises(InvalidEvidence):load_bytes(b'{"number":NaN}')


if __name__=='__main__':unittest.main()
