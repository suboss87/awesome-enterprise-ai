"""Local workspace trust boundary and edited-replay tests, without provider calls."""
import http.client
import json
import re
import threading
import unittest
from enterprise_ai.server import make_server

class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=make_server(0);cls.port=cls.server.server_port
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def request(self,method,path,body=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        connection.request(method,path,body=body,headers=headers or {})
        response=connection.getresponse();result=(response.status,response.read(),dict(response.getheaders()))
        connection.close();return result
    def session(self):
        status,body,headers=self.request('GET','/')
        self.assertEqual(status,200)
        token=re.search(b'name="workspace-token" content="([^"]+)"',body).group(1).decode()
        return {'X-Workspace-Token':token,'Content-Type':'application/json'}
    def test_host_rebinding_rejected(self):
        self.assertEqual(self.request('GET','/',headers={'Host':'evil.invalid'})[0],403)
    def test_cross_origin_rejected(self):
        headers=self.session();headers['Origin']='https://evil.invalid'
        self.assertEqual(self.request('POST','/api/run','{}',headers)[0],403)
    def test_missing_and_non_ascii_session_rejected(self):
        for token in ('','é'):
            self.assertEqual(self.request('POST','/api/run','{}',{'X-Workspace-Token':token})[0],403)
    def test_oversized_body_rejected_before_read(self):
        headers=self.session();headers['Content-Length']='500001'
        self.assertEqual(self.request('POST','/api/run',b'',headers)[0],413)
    def test_unknown_paths_are_not_filesystem_access(self):
        self.assertEqual(self.request('GET','/../enterprise_ai/provider.py')[0],404)
    def test_replay_requires_matching_example(self):
        _,raw,_=self.request('GET','/api/example/business-insights');data=json.loads(raw)
        headers=self.session();body={'project':'business-insights','mode':'replay','input':data}
        self.assertEqual(self.request('POST','/api/run',json.dumps(body),headers)[0],200)
        data['question']='Changed question'
        status,raw,_=self.request('POST','/api/run',json.dumps(body),headers)
        self.assertEqual(status,400);self.assertIn(b'unchanged example',raw)
    def test_page_does_not_cache_data_or_allow_embedding(self):
        _,_,headers=self.request('GET','/')
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])

if __name__=='__main__':unittest.main()
