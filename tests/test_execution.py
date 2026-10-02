import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from enterprise_ai.__main__ import execute
from enterprise_ai.common import InputError
from enterprise_ai.execution import execute_bounded, WorkflowFailure, _run_process, write_receipt
from enterprise_ai.catalog import ROOT


class ExecutionTests(unittest.TestCase):
    def fixture(self):
        p=ROOT/'projects/customer-resolution/examples'
        return json.loads((p/'input.json').read_text()), json.loads((p/'responses.json').read_text())

    def test_direct_call_cannot_mislabel_replay(self):
        data,responses=self.fixture()
        for mode in ('production','',None):
            with self.assertRaises(InputError): execute('customer-resolution',data,mode,responses)

    def test_direct_live_call_rejects_recorded_responses_before_inference(self):
        with patch('enterprise_ai.__main__.LiveAI') as provider:
            with self.assertRaises(InputError): execute('customer-resolution',{},'live',[])
            provider.assert_not_called()

    def test_actual_child_replay_has_identifiable_receipt(self):
        data,responses=self.fixture()
        output=execute_bounded('customer-resolution',data,'replay',responses)
        receipt=output['execution']['receipt']
        self.assertEqual(receipt['status'],'succeeded')
        self.assertEqual(receipt['mode'],'replay')
        self.assertIn('projects/customer-resolution/workflow.py',receipt['source_sha256'])
        self.assertEqual(len(receipt['input_sha256']),64)
        self.assertNotIn('input',receipt)
        self.assertEqual(receipt['calls'],[{'mode':'replay','model':None}])

    def test_rejected_input_has_sanitized_failure_receipt(self):
        with self.assertRaises(WorkflowFailure) as caught:
            execute_bounded('customer-resolution',{'secret_customer':'private'},'replay',[])
        receipt=caught.exception.receipt
        self.assertEqual(receipt['status'],'failed')
        self.assertEqual(receipt['failure_category'],'workflow_rejected')
        self.assertNotIn('private',json.dumps(receipt)+str(caught.exception))

    def test_unknown_mode_rejected_before_child(self):
        with patch('enterprise_ai.execution._run_process') as worker:
            with self.assertRaises(WorkflowFailure): execute_bounded('customer-resolution',{},'production',[])
            worker.assert_not_called()

    def test_total_deadline_kills_slow_progress_process(self):
        # Child continually produces bytes: inactivity timeout alone would not stop it.
        command=[sys.executable,'-c','import time,sys\nwhile True:\n print("tick",flush=True);time.sleep(.02)']
        started=time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired): _run_process(command,b'',.25)
        self.assertLess(time.monotonic()-started,3)

    def test_timeout_receipt_and_next_execution_recovery(self):
        with patch('enterprise_ai.execution._run_process',side_effect=subprocess.TimeoutExpired('worker',.1)):
            with self.assertRaises(WorkflowFailure) as caught: execute_bounded('customer-resolution',{},'replay',[])
        self.assertEqual(caught.exception.receipt['failure_category'],'deadline_exceeded')
        data,responses=self.fixture()
        self.assertEqual(execute_bounded('customer-resolution',data,'replay',responses)['execution']['receipt']['status'],'succeeded')

    def test_serialized_result_cap_includes_receipt(self):
        data,responses=self.fixture()
        with patch('enterprise_ai.execution.MAX_RESULT_FILE_BYTES',100):
            with self.assertRaises(WorkflowFailure) as caught:
                execute_bounded('customer-resolution',data,'replay',responses)
        self.assertEqual(caught.exception.receipt['status'],'failed')

    def test_bad_deadlines_rejected(self):
        for timeout in (0,-1,301,float('inf'),float('nan'),True):
            with self.assertRaises(InputError): execute_bounded('customer-resolution',{},deadline_seconds=timeout)

    def test_private_receipt_refuses_overwrite_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'run.json'
            write_receipt(path,{'status':'failed'})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            with self.assertRaises(FileExistsError): write_receipt(path,{})
            link=Path(tmp)/'link';link.symlink_to(path)
            with self.assertRaises(FileExistsError): write_receipt(link,{})

    def test_cli_preflight_failure_writes_private_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'bad.json'; source.write_text('{bad private data')
            receipt=Path(tmp)/'receipt.json'
            process=subprocess.run([sys.executable,'-m','enterprise_ai','run','customer-resolution','--input',str(source),'--receipt',str(receipt)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(process.returncode,2)
            self.assertEqual(json.loads(receipt.read_text())['failure_category'],'input_rejected')
            self.assertNotIn('private data',process.stderr+receipt.read_text())

    def test_worker_crash_output_is_never_accepted(self):
        result=subprocess.CompletedProcess([],1,b'{"status":"succeeded","output":{}}',b'private provider error')
        with patch('enterprise_ai.execution._run_process',return_value=result):
            with self.assertRaises(WorkflowFailure) as caught: execute_bounded('customer-resolution',{},'replay',[])
        self.assertNotIn('private',str(caught.exception))

if __name__=='__main__': unittest.main()
