"""Regressions from independent review and actual inference failures."""
import copy
import json
from pathlib import Path
import unittest
from enterprise_ai.catalog import load
from enterprise_ai.common import InputError, ReplayAI

ROOT=Path(__file__).resolve().parents[1]

class ReviewRegressions(unittest.TestCase):
    def example(self,slug):
        root=ROOT/'projects'/slug/'examples'
        return json.loads((root/'input.json').read_text()),json.loads((root/'responses.json').read_text())
    def test_free_pending_order_can_be_cancelled(self):
        data,responses=self.example('customer-resolution')
        data['order'].update(status='pending',total_cents=0,refunded_cents=0)
        data['order'].pop('delivered_on')
        data['message']['text']='Cancel this order.'
        responses[0].update(intent='cancel',evidence=[{'source_id':'msg-1','quote':'Cancel this order.'}])
        out=load('customer-resolution').run(data,ReplayAI(responses))
        self.assertNotIn('nothing_to_refund',[f['code'] for f in out['findings']])
        self.assertEqual(out['actions'][0]['status'],'awaiting_approval')
    def test_units_can_span_currencies(self):
        data,responses=self.example('business-insights')
        data['records'][1]['currency']='EUR'
        responses[0].update(measure='units',currency='')
        out=load('business-insights').run(data,ReplayAI(responses))
        self.assertEqual(out['metrics']['total'],'20')
    def test_empty_period_is_unknown_not_zero(self):
        data,responses=self.example('business-insights')
        responses[0].update(start_date='2026-09-01',end_date='2026-09-01')
        out=load('business-insights').run(data,ReplayAI(responses))
        self.assertEqual(out['answer_status'],'withheld')
        self.assertIsNone(out['metrics']['total'])
        self.assertIn('no_data',[f['code'] for f in out['findings']])
    def test_amount_sentence_punctuation_and_full_number_bounds(self):
        data,responses=self.example('claims-intake')
        field=responses[0]['documents'][1]['fields'][1]
        for quoted,accepted in [('1500.00.',True),('1,500.00.',True),('15000.00.',False),('11500.00.',False),('1500.001.',False),('-1500.00.',False),('x1500.00',False)]:
            with self.subTest(quoted=quoted):
                modified=copy.deepcopy(data)
                modified['documents'][1]['pages'][0]['text']+=' Amount '+quoted
                field['evidence'][0]['quote']='Amount '+quoted
                if accepted:load('claims-intake').run(modified,ReplayAI(copy.deepcopy(responses)))
                else:
                    with self.assertRaises(InputError):load('claims-intake').run(modified,ReplayAI(copy.deepcopy(responses)))
    def test_fabricated_claimant_value_rejected(self):
        data,responses=self.example('claims-intake')
        responses[0]['documents'][0]['fields'][0]['value']='ORG-9'
        with self.assertRaises(InputError):load('claims-intake').run(data,ReplayAI(responses))
    def test_absent_asset_history_cannot_be_fabricated(self):
        data,responses=self.example('asset-operations');data['documents']=[]
        review=responses[0]['asset_reviews'][0];review['evidence']=[]
        review['history_summary']='Replacement was completed yesterday.'
        out=load('asset-operations').run(data,ReplayAI(responses))
        self.assertNotIn('Replacement was completed',json.dumps(out))
    def test_opportunity_evidence_cannot_cross_deals(self):
        data,responses=self.example('account-intelligence')
        second=copy.deepcopy(data['opportunities'][0]);second['id']='opp-2'
        data['opportunities'].append(second)
        data['meetings'][0]['text']='opp-2: procurement is blocked.'
        responses[0]['observations']=[{'opportunity_id':data['opportunities'][0]['id'],'kind':'blocker','proposed_date':'','evidence':[{'source_id':data['meetings'][0]['id'],'quote':'procurement is blocked.'}]}]
        with self.assertRaises(InputError):load('account-intelligence').run(data,ReplayAI(responses))

if __name__=='__main__':unittest.main()
