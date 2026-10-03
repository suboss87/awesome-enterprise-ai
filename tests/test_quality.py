import copy
import json
import tempfile
import subprocess
from unittest.mock import patch
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('quality_score',ROOT/'scripts/score_projects.py')
quality=importlib.util.module_from_spec(spec);spec.loader.exec_module(quality)

class QualityTests(unittest.TestCase):
    def setUp(self):
        self.request={'questions':{'correctness':{'type':'score','criteria':['absent','tested','verified']}}}
        self.response={'model':'jev-1.13.0','answers':{'correctness':{'type':'score','score':1.5,'probabilities':{'0':0.,'1':.5,'2':.5},'confidence':.2}}}
    def test_distribution_and_fractional_score_validated(self):
        quality.validate(self.request,self.response)
    def test_high_score_cannot_disagree_with_distribution(self):
        self.response['answers']['correctness']['score']=2
        with self.assertRaises(ValueError):quality.validate(self.request,self.response)
    def test_missing_dimensions_rejected(self):
        self.response['answers']={}
        with self.assertRaises(ValueError):quality.validate(self.request,self.response)
    def test_nonfinite_probability_rejected(self):
        self.response['answers']['correctness']['probabilities']['0']=float('nan')
        with self.assertRaises(ValueError):quality.validate(self.request,self.response)
    def test_changed_question_scale_rejected(self):
        self.request['questions']['correctness']['criteria'].append('field verified')
        with self.assertRaises(ValueError):quality.validate(self.request,self.response)

class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name);self.project='customer-resolution'
        self.request={'questions':quality.read(ROOT/'quality/questions.json'),'state':{'project':self.project,'files':{'workflow.py':'original evidence'}}}
        self.manifest={'rubric_sha256':quality.digest((ROOT/'quality/rubric.json').read_bytes()),'files':{'workflow.py':quality.digest(b'original evidence')}}
        self.save()
        self.manifest['request_sha256']=quality.digest((self.folder/f'{self.project}-request.json').read_bytes())
        self.save()
    def save(self):
        (self.folder/f'{self.project}-request.json').write_text(json.dumps(self.request))
        (self.folder/f'{self.project}-manifest.json').write_text(json.dumps(self.manifest))
    def test_bound_evidence_accepted(self):
        quality.validate_bundle(self.folder,self.project)
    def test_reordered_levels_cannot_reuse_rubric_identity(self):
        self.request['questions']['correctness']['criteria'].reverse();self.save()
        with self.assertRaises(ValueError):quality.validate_bundle(self.folder,self.project)
    def test_project_substitution_rejected(self):
        self.request['state']['project']='claims-intake';self.save()
        with self.assertRaises(ValueError):quality.validate_bundle(self.folder,self.project)
    def test_source_substitution_rejected(self):
        self.request['state']['files']['workflow.py']='different evidence';self.save()
        with self.assertRaises(ValueError):quality.validate_bundle(self.folder,self.project)
    def test_missing_source_rejected(self):
        self.request['state']['files']={};self.save()
        with self.assertRaises(ValueError):quality.validate_bundle(self.folder,self.project)

    def test_changed_evaluation_rejected(self):
        self.request['state']['evaluation']={'case1':{'passed':True}};self.save()
        with self.assertRaises(ValueError):quality.validate_bundle(self.folder,self.project)
    def test_legacy_bundle_cannot_be_newly_assessed(self):
        del self.manifest['request_sha256'];self.save()
        with self.assertRaises(ValueError):quality.validate_bundle(self.folder,self.project)

class CheckoutTests(unittest.TestCase):
    def test_real_uncommitted_source_cannot_be_labeled_as_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            subprocess.run(['git','init','-q'],cwd=root,check=True)
            source=root/'workflow.py';source.write_text('original')
            subprocess.run(['git','add','workflow.py'],cwd=root,check=True)
            subprocess.run(['git','-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture'],cwd=root,check=True)
            quality.require_clean_checkout(root)
            source.write_text('uncommitted change')
            with self.assertRaises(ValueError):quality.require_clean_checkout(root)

class PreparationTests(unittest.TestCase):
    def test_targeted_batch_requires_exact_context_and_excludes_unrelated_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);source=base/'context.json';folder=base/'assessment'
            context={'verification':{'tests':'observed'},'projects':{'customer-resolution':[]}}
            source.write_text(json.dumps(context))
            with patch.object(quality,'require_clean_checkout'):
                quality.prepare(folder,source,['customer-resolution'])
                with self.assertRaises(ValueError):quality.prepare(base/'wrong',source,['claims-intake'])
            request,_=quality.validate_bundle(folder,'customer-resolution')
            self.assertEqual(1,len(list(folder.glob('*-request.json'))))
            self.assertNotIn('enterprise_ai/proposal_sources.py',request['state']['files'])
            self.assertFalse((folder/'claims-intake-request.json').exists())

    def test_summary_cannot_hide_a_missing_project_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            (base/'context.json').write_text(json.dumps({'projects':{'customer-resolution':[]}}))
            with self.assertRaisesRegex(ValueError,'manifests differ'):quality.summarize(base)

    def test_legacy_batch_cannot_shrink_when_context_is_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            (base/'customer-resolution-manifest.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'manifests differ'):quality.summarize(base)

    def test_compact_context_roundtrip_and_rejection_of_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);source=base/'compact.json';folder=base/'assessment'
            context={'verification':{'tests':'observed'},'shared_gaps':['no target deployment'],'projects':{slug:[] for slug in quality.SLUGS}}
            source.write_text(json.dumps(context,separators=(',',':')))
            # This test exercises serialization. Checkout validation has its own real-git test.
            with patch.object(quality,'require_clean_checkout'):
                quality.prepare(folder,source)
            self.assertEqual(source.read_bytes(),(folder/'context.json').read_bytes())
            for slug in quality.SLUGS:quality.validate_bundle(folder,slug)
            path=folder/'customer-resolution-request.json';request=json.loads(path.read_text())
            request['state']['verification']={'tests':'invented different result'}
            path.write_text(json.dumps(request))
            with self.assertRaises(ValueError):quality.validate_bundle(folder,'customer-resolution')

if __name__=='__main__':unittest.main()
