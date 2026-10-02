import copy
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

if __name__=='__main__':unittest.main()
