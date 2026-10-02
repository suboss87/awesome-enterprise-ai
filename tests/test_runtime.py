import json
import unittest
from enterprise_ai.common import InputError,ReplayAI,loads,object_schema,string_schema,evidence,number
from enterprise_ai.provider import LiveAI,MODEL,NoRedirect


class RuntimeTests(unittest.TestCase):
    def test_huge_integer_is_validation_error(self):
        with self.assertRaises(InputError):number(10**400)
    def test_redirect_cannot_forward_credentials(self):
        with self.assertRaises(InputError):NoRedirect().redirect_request(None,None,302,'redirect',{},'https://elsewhere.invalid')
    def test_float_exponent_overflow(self):
        with self.assertRaises(InputError):loads('{"x":1e400}')
    def test_duplicate_json_keys(self):
        with self.assertRaises(InputError):loads('{"x":1,"x":2}')
    def test_nonfinite_json(self):
        with self.assertRaises(InputError):loads('{"x":NaN}')
    def test_provider_failures_never_replay(self):
        ai=LiveAI(lambda _: {'status':'incomplete','model':MODEL})
        with self.assertRaises(InputError):ai.ask('analyze',{},object_schema({'answer':string_schema()}))
        self.assertEqual(ai.calls,[])
    def test_refusal_is_not_empty_answer(self):
        ai=LiveAI(lambda _: {'status':'completed','model':MODEL,'id':'r1','output':[{'content':[{'type':'refusal'}]}]})
        with self.assertRaises(InputError):ai.ask('analyze',{},object_schema({'answer':string_schema()}))
    def test_schema_rejects_extra_fields(self):
        ai=ReplayAI([{'answer':'ok','execute':'refund'}])
        with self.assertRaises(InputError):ai.ask('analyze',{},object_schema({'answer':string_schema()}))
    def test_provider_metadata_and_boundary(self):
        def provider(body):
            self.assertFalse(body['store']);self.assertIn('untrusted',body['input'][0]['content'])
            return {'id':'response1','model':MODEL,'status':'completed','output':[{'content':[{'type':'output_text','text':'{"answer":"ok"}'}]}],'usage':{'input_tokens':10}}
        ai=LiveAI(provider);self.assertEqual(ai.ask('analyze',{},object_schema({'answer':string_schema()})),{'answer':'ok'})
        self.assertEqual(len(ai.calls[0]['schema_sha256']),64);self.assertEqual(ai.calls[0]['mode'],'live');self.assertEqual(ai.calls[0]['response_id'],'response1')
    def test_unknown_citation(self):
        with self.assertRaises(InputError):evidence([{'source_id':'invented','quote':'text'}],{'s1':'text'})
    def test_quote_substitution(self):
        with self.assertRaises(InputError):evidence([{'source_id':'s1','quote':'approved'}],{'s1':'pending'})


if __name__=='__main__':unittest.main()
