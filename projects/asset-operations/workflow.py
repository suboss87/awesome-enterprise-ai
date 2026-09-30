"""Threshold monitoring and sourced maintenance history, not predictive diagnosis."""
from datetime import datetime
from enterprise_ai.common import *

SPEC={'id':'asset-operations','title':'Equipment Monitoring Workbench','category':'Manufacturing','summary':'Connect persistent threshold breaches to documented maintenance history for review.'}

def timestamp(value):
    text(value,'timestamp',40)
    try: d=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError as exc: raise InputError('Invalid timestamp') from exc
    if d.tzinfo is None: raise InputError('Timezone required')
    return d

def run(data,ai):
    obj(data,['as_of','assets','readings','documents'])
    now=timestamp(data['as_of']);assets=rows(data['assets'],'assets',100,1);index=unique(assets)
    for asset in assets:
        obj(asset,['id','metric','unit','upper_threshold','persistence','max_age_seconds','max_gap_seconds'])
        text(asset['metric'],'metric',100);text(asset['unit'],'unit',40);number(asset['upper_threshold'])
        integer(asset['persistence'],'persistence',1,100);integer(asset['max_age_seconds'],'max_age_seconds',1,604800);integer(asset['max_gap_seconds'],'max_gap_seconds',1,604800)
    readings=rows(data['readings'],'readings',500);unique(readings)
    groups={a:[] for a in index};seen=set()
    for reading in readings:
        obj(reading,['id','asset_id','at','value'])
        text(reading['asset_id'],'asset_id',128)
        if reading['asset_id'] not in index: raise InputError('Unknown reading asset')
        at=timestamp(reading['at']);number(reading['value'])
        if at>now: raise InputError('Future sensor reading')
        key=(reading['asset_id'],at)
        if key in seen: raise InputError('Duplicate asset timestamp')
        seen.add(key);groups[reading['asset_id']].append(reading)
    statuses=[];findings=[]
    for aid,group in groups.items():
        asset=index[aid];group.sort(key=lambda r:timestamp(r['at']))
        status='no_data';streak=0
        if group:
            latest=timestamp(group[-1]['at'])
            for pos in range(len(group)-1,-1,-1):
                r=group[pos]
                if r['value']<=asset['upper_threshold']: break
                if pos<len(group)-1 and (timestamp(group[pos+1]['at'])-timestamp(r['at'])).total_seconds()>asset['max_gap_seconds']: break
                streak+=1
            status='stale' if (now-latest).total_seconds()>asset['max_age_seconds'] else ('persistent_breach' if streak>=asset['persistence'] else 'transient_breach' if streak else 'within_threshold')
        statuses.append({'asset_id':aid,'status':status,'consecutive_high_readings':streak,'latest_reading':group[-1] if group else None})
        if status!='within_threshold': findings.append(finding(status,'review','Sensor observation requires review',aid,[r['id'] for r in group[-asset['persistence']:]]))
    documents=rows(data['documents'],'documents',200);unique(documents)
    for document in documents:
        obj(document,['id','asset_id','kind','text'])
        text(document['asset_id'],'asset_id',128)
        if document['asset_id'] not in index or document['kind'] not in ('manual_excerpt','work_order','operator_note'): raise InputError('Unsupported asset document')
        text(document['text'])
    schema=object_schema({'asset_reviews':array_schema(object_schema({'asset_id':string_schema(),'history_summary':string_schema(),'evidence':EVIDENCE_SCHEMA,'missing_information':array_schema(string_schema())}))})
    model=ai.ask('For each asset summarize only documented maintenance history/context, cite exact quotes from that asset documents. If no documents exist, use no evidence and say documentation missing. Identify missing information for a qualified maintenance reviewer. Do not infer root cause or predict failure. Do not provide repair, shutdown, safety, or operating instructions. Sensor flags are observations, not diagnoses.',{'assets':assets,'statuses':statuses,'documents':documents},schema)
    reviews=model['asset_reviews'];unique(reviews,'asset_id')
    if {r['asset_id'] for r in reviews}!=set(index): raise InputError('Asset review coverage mismatch')
    for r in reviews:
        sources={d['id']:d['text'] for d in documents if d['asset_id']==r['asset_id']}
        text(r['history_summary']);evidence(r['evidence'],sources)
        if sources and not r['evidence']: raise InputError('Available maintenance context requires evidence')
        for question in rows(r['missing_information'],'missing_information',20): text(question)
        if not sources and not r['missing_information']: raise InputError('Missing asset documents must be disclosed')
        if not sources:
            # No prose about history can be supported when there are no records.
            r['history_summary']='No maintenance documents supplied for this asset.'
    return result(SPEC['id'],'Configured thresholds evaluated; no failure prediction or operational instructions.',{'assets':len(assets),'persistent_breaches':sum(s['status']=='persistent_breach' for s in statuses),'unavailable_assets':sum(s['status'] in ('no_data','stale') for s in statuses)},findings,[{'type':'maintenance_review','asset_id':s['asset_id'],'status':s['status']} for s in statuses if s['status']!='within_threshold'],statuses=statuses,analysis=model)
