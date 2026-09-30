import copy
import json
from pathlib import Path
import unittest
from enterprise_ai.catalog import load
from enterprise_ai.common import ReplayAI,InputError

ROOT=Path(__file__).resolve().parents[1]


class ClaimsTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((ROOT/'examples/input.json').read_text())
        self.answer=json.loads((ROOT/'examples/responses.json').read_text())[0]
    def run_case(self):
        return load('claims-intake').run(self.data,ReplayAI([self.answer]))
    def test_complete_still_requires_adjuster(self):
        out=self.run_case();self.assertEqual(out['metrics']['incomplete_requirements'],0)
        self.assertTrue(out['human_review_required']);self.assertEqual(out['decision'],'NO_COVERAGE_OR_PAYMENT_DECISION')
    def test_missing_document_requests_information(self):
        self.data['documents'].pop();self.answer['documents'].pop()
        out=self.run_case();self.assertEqual(out['metrics']['incomplete_requirements'],1)
        self.assertTrue(out['actions'][0]['requires_approval'])
    def test_wrong_claimant_document_cannot_satisfy_checklist(self):
        self.data['claim']['claimant_id']='ORG-9'
        out=self.run_case();self.assertEqual(out['metrics']['incomplete_requirements'],2)
    def test_amount_discrepancy_is_not_denial(self):
        self.data['claim']['amount']='1700.00';out=self.run_case()
        self.assertIn('amount_difference',[f['code'] for f in out['findings']])
        self.assertEqual(out['decision'],'NO_COVERAGE_OR_PAYMENT_DECISION')
    def test_empty_packet(self):
        self.data['documents']=[];out=load('claims-intake').run(self.data,ReplayAI([]))
        self.assertEqual(out['metrics']['incomplete_requirements'],2)
    def test_missing_field_not_completed(self):
        self.answer['documents'][1]['fields'].pop()
        self.assertEqual(self.run_case()['metrics']['incomplete_requirements'],1)
    def test_cross_document_citation_rejected(self):
        self.answer['documents'][1]['fields'][0]['evidence']=[{'source_id':'P1','quote':'Claimant ORG-8.'}]
        with self.assertRaises(InputError):self.run_case()
    def test_fabricated_quote_rejected(self):
        self.answer['documents'][0]['fields'][0]['evidence'][0]['quote']='ALL CLAIMS APPROVED'
        with self.assertRaises(InputError):self.run_case()
    def test_unsubstantiated_type_rejected(self):
        self.answer['documents'][0]['evidence']=[]
        with self.assertRaises(InputError):self.run_case()
    def test_model_cannot_omit_document(self):
        self.answer['documents'].pop()
        with self.assertRaises(InputError):self.run_case()
    def test_duplicate_field_rejected(self):
        self.answer['documents'][0]['fields'].append(copy.deepcopy(self.answer['documents'][0]['fields'][0]))
        with self.assertRaises(InputError):self.run_case()
    def test_duplicate_pages_rejected(self):
        self.data['documents'][1]['pages'][0]['id']='P1'
        with self.assertRaises(InputError):self.run_case()
    def test_unsupported_requirements_rejected(self):
        self.data['requirements'][0]['required_fields']=['coverage_approved']
        with self.assertRaises(InputError):self.run_case()
    def test_no_silent_merging_partial_documents(self):
        partial=copy.deepcopy(self.data['documents'][1]);partial['id']='D3';partial['pages'][0]['id']='P3'
        self.data['documents'].append(partial)
        extracted=copy.deepcopy(self.answer['documents'][1]);extracted['document_id']='D3'
        extracted['evidence'][0]['source_id']='P3'
        for f in extracted['fields']:
            for e in f['evidence']:e['source_id']='P3'
        extracted['fields']=extracted['fields'][1:]
        self.answer['documents'][1]['fields']=self.answer['documents'][1]['fields'][:1]
        self.answer['documents'].append(extracted)
        self.assertEqual(self.run_case()['metrics']['incomplete_requirements'],1)


if __name__=='__main__':unittest.main()
