"""Read-only incident timeline and competing explanations."""
from datetime import datetime
from enterprise_ai.common import *

SPEC={'id':'incident-operations','title':'Incident Investigation Workbench','category':'IT operations','summary':'Reconstruct an incident and challenge explanations against supplied evidence.'}

def stamp(value):
    text(value,'timestamp',40)
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError as exc:
        raise InputError('Invalid timestamp') from exc
    if parsed.tzinfo is None:
        raise InputError('Timestamp must include timezone')
    return parsed

def run(data,ai):
    obj(data,['incident_id','window_start','window_end','events'])
    text(data['incident_id'],'incident_id',128)
    start,end=stamp(data['window_start']),stamp(data['window_end'])
    if start>=end: raise InputError('Incident window must increase')
    events=rows(data['events'],'events',200,1); unique(events)
    for item in events:
        obj(item,['id','at','kind','service','text'])
        if item['kind'] not in ('alert','deployment','log','trace','operator_note'): raise InputError('Unsupported event kind')
        text(item['service'],'service',128);text(item['text'])
        if not start<=stamp(item['at'])<=end: raise InputError('Event outside incident window')
    timeline=sorted(events,key=lambda e:(stamp(e['at']),e['id']))
    sources={e['id']:e['text'] for e in events}
    schema=object_schema({'hypotheses':array_schema(object_schema({'explanation':string_schema(),'support':EVIDENCE_SCHEMA,'contradictions':EVIDENCE_SCHEMA,'missing_checks':array_schema(string_schema())})), 'unresolved_questions':array_schema(string_schema())})
    model=ai.ask('Investigate only this saved incident window. Return at most 5 competing hypotheses, never confirmed causes. Every hypothesis needs exact supporting quotes from an event text field, using its exact id as source_id. Event timestamps, services and kinds provide context but are not quotable text. A contradiction must be an observation incompatible with the specific hypothesis; co-occurrence, alternative explanations, missing evidence and deployment proximity are not contradictions. Put uncertainty in missing_checks, not contradictions; actively report contradictory observations. Missing checks must be observational questions, not commands or remediation instructions. Deployment proximity alone does not establish causation. If evidence is insufficient return no hypotheses and explain missing information in unresolved_questions.',{'timeline':timeline},schema)
    rows(model['hypotheses'],'hypotheses',5)
    for h in model['hypotheses']:
        text(h['explanation']);evidence(h['support'],sources);evidence(h['contradictions'],sources)
        if not h['support']: raise InputError('Hypothesis requires source evidence')
        for question in rows(h['missing_checks'],'missing_checks',10): text(question)
    for question in rows(model['unresolved_questions'],'unresolved_questions',20): text(question)
    findings=[]
    if len({e['kind'] for e in events})==1: findings.append(finding('single_signal_type','review','Limited observation coverage','Only one event kind was supplied.'))
    if not model['hypotheses']: findings.append(finding('insufficient_evidence','review','No supported hypothesis','More observations are needed before attributing a cause.'))
    if any(h['contradictions'] for h in model['hypotheses']): findings.append(finding('contradictory_evidence','review','Competing evidence requires review','Do not select a cause solely by event proximity.'))
    return result(SPEC['id'],'Incident evidence assembled; all causal explanations remain hypotheses.',{'events':len(events),'services':len({e['service'] for e in events}),'hypotheses':len(model['hypotheses'])},findings,[{'type':'review_hypotheses','detail':'Compare supporting and contradictory observations with the incident owner.'}],timeline=timeline,analysis=model,incident_id=data['incident_id'])
