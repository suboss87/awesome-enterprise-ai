"""Run frozen synthetic or adopter-supplied cases through actual model inference.

Stores private per-case requests/results and checks declared observable invariants.
Passing these checks alone does not establish semantic accuracy or deployment fitness.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from enterprise_ai.catalog import load,SLUGS
from enterprise_ai.common import InputError
from enterprise_ai.provider import LiveAI


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases',type=Path,action='append',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--workers',type=int,default=3)
    args=parser.parse_args()
    if not 1<=args.workers<=4:
        parser.error('Use one to four workers')
    os.umask(0o077)
    args.output.mkdir(parents=True,exist_ok=False,mode=0o700)
    cases=[];hashes={}
    for path in args.cases:
        raw=path.read_bytes();hashes[str(path)]=hashlib.sha256(raw).hexdigest()
        cases.extend(json.loads(raw)['cases'])
    identities=[(c['project'],c['id']) for c in cases]
    if len(set(identities))!=len(identities):
        raise ValueError('Duplicate evaluation cases')
    for case in cases:
        if case['project'] not in SLUGS or not case['id'].replace('-','').replace('_','').isalnum():
            raise ValueError('Invalid case identity')
    source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [*ROOT.glob('enterprise_ai/*.py'),*ROOT.glob('projects/*/workflow.py')]}
    manifest={'started_at':datetime.now(timezone.utc).isoformat(),'cases':hashes,'source_hashes':source_hashes,
              'limits':'Frozen reference trials. Automatic invariants and semantic review are separate. No production validation.'}
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    def run(case):
        folder=args.output/(case['project']+'--'+case['id']);folder.mkdir()
        (folder/'case.json').write_text(json.dumps(case,indent=2))
        ai=LiveAI();count=0;send=ai._send
        def transport(body):
            nonlocal count
            count+=1
            (folder/f'request-{count}.json').write_text(json.dumps(body,indent=2))
            response=send(body)
            (folder/f'response-{count}.json').write_text(json.dumps(response,indent=2))
            return response
        ai.transport=transport
        row={'project':case['project'],'id':case['id'],'passed':False,'differences':[],
             'semantic_review_required':True}
        try:
            output=load(case['project']).run(case['input'],ai)
            output['execution']={'mode':'live','calls':ai.calls}
            (folder/'output.json').write_text(json.dumps(output,indent=2))
            expected=case['expected'];codes={f['code'] for f in output['findings']}
            for key,value in expected.get('metrics',{}).items():
                if output['metrics'].get(key)!=value:
                    row['differences'].append({'metric':key,'expected':value,'actual':output['metrics'].get(key)})
            for code in expected.get('required_findings',[]):
                if code not in codes:row['differences'].append({'missing_finding':code})
            for code in expected.get('forbidden_findings',[]):
                if code in codes:row['differences'].append({'unexpected_finding':code})
            for alternatives in expected.get('any_findings',[]):
                if not codes.intersection(alternatives):row['differences'].append({'missing_any_finding':alternatives})
            for path,wanted in expected.get('paths',{}).items():
                actual=output
                for key in path.split('.'):
                    actual=actual.get(key) if isinstance(actual,dict) else None
                if actual!=wanted:row['differences'].append({'path':path,'expected':wanted,'actual':actual})
            row['passed']=not row['differences']
            row['model_calls']=len(ai.calls)
        except Exception as exc:
            row['error_type']=type(exc).__name__
            row['error']=str(exc) if isinstance(exc,InputError) else 'Unhandled failure; inspect code with the saved input'
        (folder/'check.json').write_text(json.dumps(row,indent=2))
        print(json.dumps(row),flush=True)
        return row
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results=list(pool.map(run,cases))
    report={'automatic_checks_passed':sum(r['passed'] for r in results),'cases':len(results),'results':results,
            'semantic_review':'Required separately, including cases whose checks test deterministic behavior only.'}
    (args.output/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='results'}),flush=True)


if __name__=='__main__':main()
