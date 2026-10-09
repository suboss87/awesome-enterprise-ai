"""Compare a live business planner with narrow rules and a supplied-plan oracle.

Only synthetic or authorized cases may be sent to the model. Labels and source
hashes are frozen before calls. Failures are retained, never retried or dropped.
The rules baseline was developed with visible synthetic questions; this is not
a blind comparison or a representative enterprise validation.
"""
import argparse
import calendar
import copy
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from enterprise_ai.catalog import load
from enterprise_ai.common import ReplayAI,InputError
from enterprise_ai.provider import LiveAI, MODEL


def save(path,value):
    with path.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def normalize(plan,data):
    if plan['status']=='clarify':return {'status':'clarify'}
    value={k:plan[k] for k in ('status','measure','group_by','start_date','end_date','currency','regions','products')}
    for key,boundary in [('start_date','coverage_start'),('end_date','coverage_end')]:
        value[key]=value[key] or data['source_snapshot'][boundary]
    currencies={r['currency'] for r in data['records']}
    if not value['currency'] and value['measure']!='units' and len(currencies)==1:
        value['currency']=next(iter(currencies))
    for key in ('regions','products'):value[key]=sorted(set(value[key]))
    return value


def table(rows):
    return sorted([{**r,'record_ids':sorted(r['record_ids'])} for r in rows],key=lambda r:r['group'])


def compare(output,expected,data,*,allow_safe_clarification=False):
    actual_plan=normalize(output['plan'],data)
    plan_agreement=actual_plan==normalize(expected['plan'],data)
    status_agreement=output['answer_status']==expected['answer_status']
    metric_agreement=all(k in output['metrics'] and output['metrics'][k]==v for k,v in expected['metrics'].items())
    return {'strict_plan_agreement':plan_agreement,'answer_status_agreement':status_agreement,
        'metrics_agreement':metric_agreement,'table_agreement':table(output['table'])==table(expected['table']),
        'false_ready':expected['answer_status']=='withheld' and output['answer_status']=='calculated',
        'safe_clarification_equivalent':allow_safe_clarification and expected['plan']['status']=='ready' and actual_plan['status']=='clarify' and status_agreement}


def oracle(case):
    plan=copy.deepcopy(case['expected']['plan'])
    if plan['status']=='clarify':
        plan.update(measure='revenue',group_by='none',start_date='',end_date='',currency='',regions=[],products=[])
    plan.update(question_quote=case['input']['question'],clarification='Define a supported unambiguous analysis.' if plan['status']=='clarify' else '')
    return plan


def narrow_rules(data):
    """Conservative lexical metric/date/filter parser; no model or arithmetic."""
    question=data['question'];q=question.lower()
    plan={'status':'clarify','measure':'revenue','group_by':'none','start_date':'','end_date':'',
        'currency':'','regions':[],'products':[],'question_quote':question,'clarification':'Use a supported metric, calendar period and grouping.'}
    if re.search(r'\b(margin|percentage|forecast|growth|average|salesperson|profitable)\b',q):return plan
    if 'gross profit' in q:measure='gross_profit'
    elif 'net revenue' in q or 'revenue minus refunds' in q:measure='net_revenue'
    elif 'recorded cost' in q:measure='cost'
    elif 'gross revenue' in q:measure='revenue'
    elif 'recorded units' in q:measure='units'
    else:return plan
    group='none'
    if 'by calendar month' in q or 'by month' in q:group='month'
    elif 'by region' in q:group='region'
    elif 'by product' in q:group='product'
    elif re.search(r'\b(by|separately for each)\b',q):return plan
    plan.update(measure=measure,group_by=group)
    codes=re.findall(r'\b[A-Z]{3}\b',question)
    if len(set(codes))>1:return plan
    plan['currency']=codes[0] if codes else ''
    for name in ('region','product'):
        match=re.search(r'(?<!by )\b'+name+r'\s+([A-Za-z]+)\b',question,re.I)
        if match:plan[name+'s']=[match.group(1)]
    if 'start of this month' in q and 'supplied business date' in q:
        today=date.fromisoformat(data['as_of']);plan.update(start_date=today.replace(day=1).isoformat(),end_date=today.isoformat())
    elif 'entire declared complete coverage' not in q:
        month_names='|'.join(calendar.month_name[1:])
        span=re.search(r'('+month_names+r')\s+(\d{1,2})\s+(?:through|to)\s+('+month_names+r')\s+(\d{1,2}),?\s+(\d{4})',question,re.I)
        single=re.search(r'('+month_names+r')\s+(\d{1,2}),?\s+(\d{4})\s+only',question,re.I)
        month=re.search(r'('+month_names+r')\s+(\d{4})',question,re.I)
        months={name.lower():i for i,name in enumerate(calendar.month_name) if name}
        try:
            if span:
                m1,d1,m2,d2,y=span.groups();plan.update(start_date=date(int(y),months[m1.lower()],int(d1)).isoformat(),end_date=date(int(y),months[m2.lower()],int(d2)).isoformat())
            elif single:
                m,d,y=single.groups();value=date(int(y),months[m.lower()],int(d)).isoformat();plan.update(start_date=value,end_date=value)
            elif month:
                m,y=month.groups();m=months[m.lower()];y=int(y);plan.update(start_date=date(y,m,1).isoformat(),end_date=date(y,m,calendar.monthrange(y,m)[1]).isoformat())
            else:return plan
        except ValueError:return plan
    plan.update(status='ready',clarification='')
    return plan


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--offline',action='store_true',help='Only rules and supplied-plan checks; no live measurement')
    args=parser.parse_args()
    raw=args.cases.read_bytes();corpus=json.loads(raw);cases=corpus['cases']
    if len({c['id'] for c in cases})!=len(cases):raise ValueError('Duplicate case IDs')
    os.umask(0o077);args.output.mkdir(parents=True,exist_ok=False,mode=0o700)
    source_paths=[Path(__file__),ROOT/'projects/business-insights/workflow.py',ROOT/'enterprise_ai/provider.py',ROOT/'enterprise_ai/common.py',ROOT/'enterprise_ai/catalog.py']
    source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    save(args.output/'manifest.json',{'started_at':datetime.now(timezone.utc).isoformat(),
        'cases_sha256':hashlib.sha256(raw).hexdigest(),'model':MODEL,'offline':args.offline,
        'source_sha256':source_hashes,
        'provenance':corpus['provenance'],
        'protocol':'Freeze labels/config before calls. Exact normalized plan, answer status, expected metrics, tables and false-ready rate are separate. Mixed-currency and unknown-filter clarification may safely withhold while failing strict plan agreement. Failures remain in every denominator. Rules use visible questions; oracle is not human performance.'})
    (args.output/'cases.json').write_bytes(raw)
    workflow=load('business-insights');results=[]
    for index,case in enumerate(cases):
        for mode in (['oracle','rules'] if args.offline else ['oracle','rules','live']):
            folder=args.output/f'{index:02}-{mode}';folder.mkdir();started=time.monotonic()
            ai=LiveAI() if mode=='live' else ReplayAI([oracle(case) if mode=='oracle' else narrow_rules(case['input'])])
            if mode=='live':
                send=ai._send
                def transport(body):
                    save(folder/'request.json',body)
                    response=send(body);save(folder/'response.json',response);return response
                ai.transport=transport
            row={'id':case['id'],'mode':mode}
            try:
                output=workflow.run(copy.deepcopy(case['input']),ai)
                save(folder/'output.json',output);row.update(compare(output,case['expected'],case['input'],
                    allow_safe_clarification=case['id'] in ('money-currency-unspecified','missing-region-not-zero')))
            except Exception as exc:
                row.update(error_type=type(exc).__name__,error=str(exc) if isinstance(exc,InputError) else 'Unhandled evaluator failure; inspect frozen input and source.',strict_plan_agreement=False,answer_status_agreement=False,
                    metrics_agreement=False,table_agreement=False,false_ready=False,safe_clarification_equivalent=False)
            row.update(latency_seconds=round(time.monotonic()-started,4),calls=ai.calls)
            if (folder/'response.json').exists():
                row['provider_usage']=json.loads((folder/'response.json').read_text()).get('usage')
            save(folder/'check.json',row);results.append(row);print(json.dumps(row),flush=True)
    summaries={}
    for mode in sorted({r['mode'] for r in results}):
        group=[r for r in results if r['mode']==mode]
        summaries[mode]={'cases':len(group),'failures':sum('error_type' in r for r in group),
            'expected_withheld_cases':sum(c['expected']['answer_status']=='withheld' for c in cases),
            **{key:sum(r[key] for r in group) for key in ('strict_plan_agreement','answer_status_agreement','metrics_agreement','table_agreement','false_ready','safe_clarification_equivalent')},
            'mean_latency_seconds':round(sum(r['latency_seconds'] for r in group)/len(group),4)}
    final_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    save(args.output/'report.json',{'summaries':summaries,'results':results,'final_source_sha256':final_hashes,
        'frozen_source_unchanged':source_hashes==final_hashes,'limits':corpus['provenance']['limits']})
    print(json.dumps(summaries),flush=True)


if __name__=='__main__':main()
