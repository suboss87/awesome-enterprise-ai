"""Exact inventory matching with advisory interpretation, never a scanner."""
from enterprise_ai.common import *

SPEC={'id':'exposure-review','title':'Vulnerability Remediation Planner','category':'Security','summary':'Separate known version matches from missing inventory and prepare advisory review.'}

def run(data,ai):
    obj(data,['inventory_complete','inventory','advisories','findings'])
    if type(data['inventory_complete']) is not bool: raise InputError('inventory_complete must be boolean')
    inventory=rows(data['inventory'],'inventory',300); inv=unique(inventory)
    for item in inventory:
        obj(item,['id','package','version','service','owner'])
        for key in ('package','version','service','owner'): text(item[key],key,200)
    advisories=rows(data['advisories'],'advisories',100,1); adv=unique(advisories)
    for item in advisories:
        obj(item,['id','package','affected_versions','fixed_versions','text'])
        text(item['package'],'package',200);text(item['text'])
        for field in ('affected_versions','fixed_versions'):
            values=rows(item[field],field,100)
            for version in values: text(version,'version',128)
            if len(values)!=len(set(values)): raise InputError('Duplicate version')
        if set(item['affected_versions']) & set(item['fixed_versions']): raise InputError('Conflicting advisory version lists')
    scans=rows(data['findings'],'findings',200,1); unique(scans)
    matches=[]
    for scan in scans:
        obj(scan,['id','inventory_id','advisory_id'])
        text(scan['inventory_id'],'inventory_id',128);text(scan['advisory_id'],'advisory_id',128)
        if scan['advisory_id'] not in adv: raise InputError('Unknown advisory')
        a=adv[scan['advisory_id']];asset=inv.get(scan['inventory_id'])
        state='unknown_inventory'
        if asset:
            if asset['package']!=a['package']: state='package_mismatch'
            elif asset['version'] in a['affected_versions']: state='affected_version_match'
            elif asset['version'] in a['fixed_versions']: state='fixed_version_match'
            else: state='version_unlisted'
        matches.append({'finding_id':scan['id'],'inventory_id':scan['inventory_id'],'advisory_id':a['id'],'status':state,'owner':asset['owner'] if asset else None,'service':asset['service'] if asset else None,'advisory_fixed_versions':a['fixed_versions']})
    schema=object_schema({'advisories':array_schema(object_schema({'advisory_id':string_schema(),'impact_summary':string_schema(),'preconditions':array_schema(string_schema()),'review_questions':array_schema(string_schema()),'evidence':EVIDENCE_SCHEMA}))})
    interpreted=ai.ask('Interpret each advisory supplied, exactly once. Evidence source_id must be exactly the advisory id, with quote copied verbatim ONLY from that advisory text field. Matches, package/version arrays and other JSON metadata are context, not quotable sources. Do not add id prefixes. Quote advisory text for impact and contextual preconditions; use review_questions for unknowns. Do not infer installed software, version applicability, exploitability, fixes, or vendor backports beyond the provided deterministic matches. No exploitation or remediation execution instructions.',{'advisories':advisories,'matches':matches},schema)
    records=interpreted['advisories']; unique(records,'advisory_id')
    if {r['advisory_id'] for r in records}!=set(adv): raise InputError('Advisory interpretations must cover input exactly')
    for r in records:
        text(r['impact_summary']);evidence(r['evidence'],{r['advisory_id']:adv[r['advisory_id']]['text']})
        if not r['evidence']: raise InputError('Advisory interpretation requires evidence')
        for key in ('preconditions','review_questions'):
            for value in rows(r[key],key,20): text(value)
    findings=[]
    if not data['inventory_complete'] or not inventory: findings.append(finding('inventory_incomplete','review','Inventory coverage is unknown','Missing software cannot be classified as safe.'))
    for match in matches:
        if match['status']!='fixed_version_match': findings.append(finding(match['status'],'review','Finding requires owner review',match['finding_id'],[match['finding_id'],match['advisory_id']]))
    return result(SPEC['id'],'Version evidence and advisory context prepared; no exploitability clearance.',{'findings':len(matches),'affected_matches':sum(m['status']=='affected_version_match' for m in matches),'unknown_matches':sum(m['status'] in ('unknown_inventory','version_unlisted','package_mismatch') for m in matches)},findings,[{'type':'owner_review','finding_id':m['finding_id'],'owner':m['owner']} for m in matches],matches=matches,analysis=interpreted)
