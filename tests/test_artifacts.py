"""Private operator artifacts: actual CLI journeys and publication failures."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from enterprise_ai.catalog import ROOT,SLUGS
from enterprise_ai.execution import write_receipt,write_run_artifacts


class ArtifactTests(unittest.TestCase):
    def cli(self,slug,directory,*extra):
        p=ROOT/'projects'/slug/'examples'
        return subprocess.run([sys.executable,'-m','enterprise_ai','run',slug,
            '--input',str(p/'input.json'),'--mode','replay','--responses',str(p/'responses.json'),
            '--run-dir',str(directory),*extra],cwd=ROOT,capture_output=True,text=True)

    def test_every_workflow_publishes_private_hash_bound_artifacts_without_records_in_logs(self):
        with tempfile.TemporaryDirectory() as temporary:
            for slug in SLUGS:
                with self.subTest(project=slug):
                    directory=Path(temporary)/slug
                    run=self.cli(slug,directory)
                    self.assertEqual(run.returncode,0,run.stderr)
                    log=json.loads(run.stdout)
                    self.assertEqual(set(log),{'status','run_id'})
                    self.assertEqual(log['status'],'succeeded')
                    self.assertEqual(run.stderr,'')
                    raw=(directory/'result.json').read_bytes()
                    result=json.loads(raw);receipt=json.loads((directory/'receipt.json').read_bytes())
                    self.assertEqual(receipt['run_id'],log['run_id'])
                    self.assertEqual(receipt['run_id'],result['execution']['receipt']['run_id'])
                    self.assertEqual(receipt['result_sha256'],hashlib.sha256(raw).hexdigest())
                    self.assertEqual(receipt['result_bytes'],len(raw))
                    self.assertIs(result['human_review_required'],True)
                    for path,mode in [(directory,0o700),(directory/'result.json',0o600),(directory/'receipt.json',0o600)]:
                        self.assertEqual(stat.S_IMODE(path.stat().st_mode),mode)

    def test_existing_directory_rejected_before_input_and_preserves_previous_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)/'run';directory.mkdir();original=directory/'result.json';original.write_text('previous reviewed result')
            run=self.cli('customer-resolution',directory,'--input',str(Path(temporary)/'missing'))
            self.assertEqual(run.returncode,2)
            self.assertEqual(original.read_text(),'previous reviewed result')
            self.assertEqual(run.stdout,'')

    def test_symlink_run_directory_is_rejected_without_touching_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            target=Path(temporary)/'target';target.mkdir();link=Path(temporary)/'link';link.symlink_to(target)
            self.assertEqual(self.cli('customer-resolution',link).returncode,2)
            self.assertEqual(list(target.iterdir()),[])

    def test_input_failure_publishes_only_sanitized_failure_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            bad=Path(temporary)/'input.json';bad.write_text('{private customer details')
            directory=Path(temporary)/'run'
            run=self.cli('customer-resolution',directory,'--input',str(bad))
            self.assertEqual(run.returncode,2)
            self.assertEqual(run.stdout,'')
            receipt=json.loads((directory/'receipt.json').read_text())
            self.assertEqual(receipt['status'],'failed')
            self.assertEqual(receipt['failure_category'],'input_rejected')
            self.assertNotIn('private customer',run.stderr+json.dumps(receipt))
            self.assertFalse((directory/'result.json').exists())

    def test_failed_atomic_publication_leaves_no_partial_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'receipt.json'
            with patch('enterprise_ai.execution.os.link',side_effect=OSError('publication failed')):
                with self.assertRaises(OSError):write_receipt(path,{'status':'failed'})
            self.assertEqual(list(Path(temporary).iterdir()),[])

    def test_receipt_failure_removes_new_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            output={'execution':{'receipt':{'status':'succeeded','run_id':'test'}}}
            with patch('enterprise_ai.execution.write_receipt',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):write_run_artifacts(temporary,output)
            self.assertEqual(list(Path(temporary).iterdir()),[])

    def test_failed_serialization_does_not_create_an_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):write_receipt(Path(temporary)/'receipt.json',{'value':float('nan')})
            self.assertEqual(list(Path(temporary).iterdir()),[])

    def test_run_directory_and_separate_receipt_cannot_be_combined(self):
        with tempfile.TemporaryDirectory() as temporary:
            run=self.cli('customer-resolution',Path(temporary)/'run','--receipt',str(Path(temporary)/'receipt.json'))
            self.assertEqual(run.returncode,2)
            self.assertEqual(list(Path(temporary).iterdir()),[])


if __name__=='__main__':unittest.main()
