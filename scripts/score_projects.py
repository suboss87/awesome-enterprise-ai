"""Prepare immutable Jev evidence bundles, assess once, and render local scores.

Run from this checkout. Only send data you are authorized to disclose to the
judge provider. Prepared requests contain repository source and synthetic evals.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from enterprise_ai.catalog import SLUGS

# Original completed assessment protocol predates context.json. Frozen for legacy
# compatibility; never infer a smaller batch from whichever files remain.
LEGACY_BATCH_PROJECTS=(
    'customer-resolution','incident-operations','exposure-review','business-insights',
    'inventory-decisions','asset-operations','claims-intake','proposal-operations',
    'account-intelligence','workforce-onboarding')


def digest(raw): return hashlib.sha256(raw).hexdigest()

def read(path): return json.loads(path.read_bytes())

def save(path,value):
    with path.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def validate(request,response):
    if not isinstance(response.get('model'),str) or not response['model'].startswith('jev-'):
        raise ValueError('Missing resolved Jev model')
    if set(response.get('answers',{}))!=set(request['questions']):
        raise ValueError('Answer keys differ from questions')
    for key,question in request['questions'].items():
        answer=response['answers'][key]
        if answer.get('type')!=question['type']: raise ValueError('Wrong answer type')
        probabilities=answer.get('probabilities',{})
        expected=set(map(str,range(len(question['criteria'])))) if question['type']=='score' else set(question['criteria'])
        if set(probabilities)!=expected: raise ValueError('Wrong probability keys')
        values=[*probabilities.values(),answer.get('confidence')]
        if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or not 0<=x<=1 for x in values):
            raise ValueError('Invalid probability/confidence')
        if abs(sum(probabilities.values())-1)>.02: raise ValueError('Invalid distribution')
        if question['type']=='score':
            score=answer.get('score');top=len(question['criteria'])-1
            if isinstance(score,bool) or not isinstance(score,(int,float)) or not math.isfinite(score) or not 0<=score<=top:
                raise ValueError('Invalid score')
            if abs(score-sum(int(k)*v for k,v in probabilities.items()))>.03: raise ValueError('Inconsistent score')
        elif answer.get('choice') not in probabilities or probabilities[answer['choice']]<max(probabilities.values()):
            raise ValueError('Inconsistent choice')


def validate_bundle(folder,project,*,allow_completed_legacy=False):
    request=read(folder/f'{project}-request.json')
    manifest=read(folder/f'{project}-manifest.json')
    request_hash=digest((folder/f'{project}-request.json').read_bytes())
    expected_hash=manifest.get('request_sha256')
    if expected_hash is None and allow_completed_legacy:
        call=read(folder/f'{project}-call.json')
        if call.get('validated') is True and (folder/f'{project}-response.json').is_file():
            expected_hash=call.get('request_sha256')
    if request_hash!=expected_hash:
        raise ValueError('Prepared request changed or lacks immutable binding')
    questions=read(ROOT/'quality/questions.json')
    rubric=read(ROOT/'quality/rubric.json')
    if request.get('questions')!=questions:
        raise ValueError('Questions differ from frozen assessment protocol')
    for key,dimension in rubric['dimensions'].items():
        if questions.get(key,{}).get('type')!='score' or questions[key].get('criteria')!=dimension['criteria']:
            raise ValueError('Question levels differ from rubric')
    if manifest.get('rubric_sha256')!=digest((ROOT/'quality/rubric.json').read_bytes()):
        raise ValueError('Changed rubric requires separate baseline')
    state=request.get('state',{})
    if state.get('project')!=project:
        raise ValueError('Evidence project identity mismatch')
    files=state.get('files',{})
    if not files or any(not isinstance(value,str) for value in files.values()):
        raise ValueError('Missing source evidence')
    if {name:digest(value.encode()) for name,value in files.items()}!=manifest.get('files'):
        raise ValueError('Evidence file hashes differ from frozen manifest')
    if 'context_sha256' in manifest:
        if digest((folder/'context.json').read_bytes())!=manifest['context_sha256']:
            raise ValueError('Verification context hash mismatch')
        context=read(folder/'context.json')
        if state.get('verification')!=context.get('verification') or state.get('known_gaps')!={'all':context.get('shared_gaps',[]),'project':context['projects'][project]}:
            raise ValueError('Request context differs from frozen verification')
    return request,manifest


def require_clean_checkout(root):
    status=subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=root,text=True)
    if status.strip():
        raise ValueError('Commit or isolate working-tree changes before preparing a revision-bound assessment')


def prepare(folder,context_path,projects=None):
    # Caller writes the actual verification and unresolved gaps before scoring.
    context=read(context_path)
    projects=list(SLUGS if projects is None else projects)
    if not projects or len(set(projects))!=len(projects) or not set(projects)<=set(SLUGS):
        raise ValueError('Select distinct known projects')
    if set(context.get('projects',{}))!=set(projects) or not context.get('verification'):
        raise ValueError('Explicit verification and exactly the selected project gaps are required')
    require_clean_checkout(ROOT)
    folder.mkdir(parents=True,exist_ok=False)
    questions=read(ROOT/'quality/questions.json')
    rubric_raw=(ROOT/'quality/rubric.json').read_bytes()
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    common=[*sorted((ROOT/'enterprise_ai').glob('*.py')),*sorted((ROOT/'tests').glob('test_*.py')),
            ROOT/'docs/DEPLOYMENT.md',ROOT/'docs/ADOPTION-ROADMAP.md']
    for slug in projects:
        project=ROOT/'projects'/slug
        paths=common+[project/'workflow.py',project/'README.md',project/'tests/test_workflow.py']
        if (project/'evaluation/cases.json').exists():paths.append(project/'evaluation/cases.json')
        if slug=='business-insights':
            paths.extend([ROOT/'scripts/evaluate_business_planner.py',
                project/'evaluation/planner-2026-10-09/cases.json',
                project/'evaluation/planner-2026-10-09/README.md',
                project/'evaluation/planner-2026-10-09/results.json'])
        if (project/'GOVERNANCE.md').exists():paths.append(project/'GOVERNANCE.md')
        # Proposal review implementation only affects this workflow. Avoid irrelevant judge context.
        paths=[p for p in paths if slug=='proposal-operations' or p.name not in ('proposal_review.py','test_proposal_review.py','proposal_sources.py','test_proposal_sources.py')]
        files={str(p.relative_to(ROOT)):p.read_text() for p in paths}
        outputs={p.name:read(p) for p in (ROOT/'evaluation/2026-09-30').glob(slug+'--*.json')}
        state={'project':slug,'scope':read(ROOT/'quality/rubric.json')['deployment_scope'],
               'files':files,'evaluation':outputs,'verification':context['verification'],
               'known_gaps':{'all':context.get('shared_gaps',[]),'project':context['projects'][slug]}}
        request={'model':'jev-latest','questions':questions,'state':state}
        save(folder/f'{slug}-request.json',request)
        save(folder/f'{slug}-manifest.json',{'commit':commit,'request_sha256':digest((folder/f'{slug}-request.json').read_bytes()),'rubric_sha256':digest(rubric_raw),
             'context_sha256':digest(context_path.read_bytes()),'files':{p:digest(text.encode()) for p,text in files.items()}})
    with (folder/'context.json').open('xb') as stream:
        stream.write(context_path.read_bytes())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): raise ValueError('Judge redirect rejected')


def assess(folder,project):
    request,_=validate_bundle(folder,project)
    path=folder/f'{project}-request.json';raw=path.read_bytes()
    response_path=folder/f'{project}-response.json';call_path=folder/f'{project}-call.json'
    # A started call is not automatically retried, including ambiguous network failures.
    if response_path.exists() or call_path.exists(): raise ValueError('Assessment already started; preserve it and investigate')
    key=os.environ.get('TYPESAFE_API_KEY')
    if not key: raise ValueError('Set TYPESAFE_API_KEY in the process environment')
    call={'request_sha256':digest(raw),'started_at':datetime.now(timezone.utc).isoformat(),
          'endpoint':'https://api.typesafe.ai/v1/systemone'}
    save(call_path,call)
    req=urllib.request.Request(call['endpoint'],raw,{'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=90) as response:
            body=response.read(2_000_001)
        if len(body)>2_000_000: raise ValueError('Judge response too large')
        with response_path.open('xb') as stream:stream.write(body)
        result=json.loads(body);validate(request,result)
        call.update(response_sha256=digest(body),model=result['model'],usage=result.get('usage'),validated=True)
    except Exception as exc:
        call['error_type']=type(exc).__name__
        raise
    finally:
        call_path.write_text(json.dumps(call,indent=2)+'\n')


def summarize(folder):
    rubric=read(ROOT/'quality/rubric.json')
    weights={k:v['weight'] for k,v in rubric['dimensions'].items()}
    if any(not math.isfinite(v) or v<=0 for v in weights.values()) or abs(sum(weights.values())-1)>1e-9:
        raise ValueError('Weights must be positive and sum to one')
    # The frozen context defines this batch, not today's growing catalog.
    context_path=folder/'context.json'
    manifest_paths=list(folder.glob('*-manifest.json'))
    # An added, unbound context cannot redefine a legacy batch.
    context_bound=bool(manifest_paths) and all('context_sha256' in read(p) for p in manifest_paths)
    projects=read(context_path).get('projects',{}) if context_path.exists() and context_bound else LEGACY_BATCH_PROJECTS
    if not projects or not set(projects)<=set(SLUGS):
        raise ValueError('Assessment context must identify known projects')
    manifests={p.name.removesuffix('-manifest.json') for p in folder.glob('*-manifest.json')}
    if manifests!=set(projects):
        raise ValueError('Assessment manifests differ from frozen project scope')
    rows=[]
    for slug in projects:
        request,manifest=validate_bundle(folder,slug,allow_completed_legacy=True)
        request_raw=(folder/f'{slug}-request.json').read_bytes()
        response_raw=(folder/f'{slug}-response.json').read_bytes();response=json.loads(response_raw)
        call=read(folder/f'{slug}-call.json');manifest=read(folder/f'{slug}-manifest.json')
        if call['request_sha256']!=digest(request_raw) or call.get('response_sha256')!=digest(response_raw):
            raise ValueError('Assessment hash mismatch')
        if manifest['rubric_sha256']!=digest((ROOT/'quality/rubric.json').read_bytes()):
            raise ValueError('Changed rubric requires separate baseline')
        validate(request,response)
        scores={k:response['answers'][k]['score'] for k in weights}
        rows.append({'project':slug,'model':response['model'],'scores':scores,
                     'weighted_100':round(sum(weights[k]*scores[k]/4*100 for k in weights),2),
                     'first_priority':response['answers']['first_priority']['choice'],
                     'request_sha256':digest(request_raw),'response_sha256':digest(response_raw),
                     'production_designation':'blocked: target-environment acceptance unverified'})
    return {'rubric_version':rubric['version'],'rubric_sha256':digest((ROOT/'quality/rubric.json').read_bytes()),
            'limits':'Uncalibrated model judgments of supplied evidence. Not measured production accuracy or deployment approval.',
            'projects':rows}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('folder',type=Path);p.add_argument('--context',required=True,type=Path);p.add_argument('--project',choices=SLUGS,action='append')
    p=sub.add_parser('assess');p.add_argument('folder',type=Path);p.add_argument('--project',choices=SLUGS,required=True)
    p=sub.add_parser('summarize');p.add_argument('folder',type=Path)
    args=parser.parse_args()
    if args.command=='prepare':prepare(args.folder,args.context,args.project)
    elif args.command=='assess':assess(args.folder,args.project)
    else:print(json.dumps(summarize(args.folder),indent=2))


if __name__=='__main__':main()
