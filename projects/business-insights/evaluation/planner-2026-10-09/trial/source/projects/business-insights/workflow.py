"""Natural-language business analysis with an allowlisted plan and exact arithmetic."""
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from enterprise_ai.common import (obj,text,rows,unique,integer,money,day,object_schema,
    array_schema,string_schema,finding,result,InputError)

SPEC={'id':'business-insights','title':'Business Insights Workbench','category':'Finance & operations',
      'summary':'Ask a business question and inspect the exact calculations behind the answer.'}
MEASURES=('revenue','net_revenue','cost','gross_profit','units')
PLAN=object_schema({'status':string_schema(['ready','clarify']),'measure':string_schema(MEASURES),
    'group_by':string_schema(['none','region','product','month']), 'start_date':string_schema(),
    'end_date':string_schema(),'currency':string_schema(),'regions':array_schema(string_schema()),
    'products':array_schema(string_schema()),'clarification':string_schema(), 'question_quote':string_schema()})
PROMPT='''Translate the question into this supported analysis plan only. Revenue means gross revenue; net_revenue subtracts refunds; gross_profit subtracts refunds and cost. Units are recorded units, not net of returns. Group by none, region, product or calendar month. Dates are inclusive; an empty start or end means the corresponding boundary of the declared complete source coverage. Never select dates outside that coverage. Use the supplied as_of for relative dates. Return exact region/product values. If unsupported measures, unclear business meaning or incompatible requested dimensions prevent an answer, status=clarify with a precise question. Never substitute a supported metric for unsupported profit margin, growth, average or forecast. Do not choose a currency for the user if several exist. Empty currency means unspecified. Quote the exact part of the user question that defines the requested analysis. No SQL or code execution.'''

SNAPSHOT_FIELDS=('source_system','snapshot_id','exported_at','data_as_of','schema_version',
                 'metric_definition_version','metric_definition_status','row_grain','coverage_start',
                 'coverage_end','completeness','freshness')


def validate_snapshot(value,as_of):
    obj(value,SNAPSHOT_FIELDS)
    for key in ('source_system','snapshot_id','exported_at','schema_version',
                'metric_definition_version','metric_definition_status','row_grain'):
        text(value[key],key,256)
    try:
        exported=datetime.fromisoformat(value['exported_at'].replace('Z','+00:00'))
    except ValueError as exc:
        raise InputError('exported_at must be an ISO-8601 timestamp') from exc
    if exported.tzinfo is None or exported.utcoffset() is None:
        raise InputError('exported_at must include a timezone offset')
    data_as_of=day(value['data_as_of'])
    if data_as_of>exported.date():
        raise InputError('data_as_of cannot follow the export date in its declared source timezone')
    coverage_start=day(value['coverage_start'])
    coverage_end=day(value['coverage_end'])
    if coverage_start>coverage_end or coverage_end>data_as_of:
        raise InputError('Snapshot coverage dates must be ordered and cannot exceed data_as_of')
    if value['completeness'] not in ('complete','partial','unknown'):
        raise InputError('completeness must be complete, partial or unknown')
    if value['freshness'] not in ('current','stale','unknown'):
        raise InputError('freshness must be current, stale or unknown')
    if value['metric_definition_status'] not in ('approved','unapproved','unknown'):
        raise InputError('metric_definition_status must be approved, unapproved or unknown')
    return coverage_start,coverage_end,data_as_of


def run(data,ai):
    obj(data,['question','as_of','records','source_snapshot'])
    question=text(data['question']);as_of=day(data['as_of'])
    coverage_start,coverage_end,data_as_of=validate_snapshot(data['source_snapshot'],as_of)
    snapshot=data['source_snapshot']
    preflight_holds=[]
    if snapshot['freshness']!='current':
        preflight_holds.append(finding('snapshot_freshness','review','Snapshot freshness is not confirmed',
            'No totals were calculated because the adapter marked this snapshot stale or its freshness unknown.'))
    if snapshot['completeness']!='complete':
        preflight_holds.append(finding('snapshot_incomplete','review','Source coverage is incomplete',
            'No totals were calculated because the source extract is partial or its completeness is unknown.'))
    if snapshot['metric_definition_status']!='approved':
        preflight_holds.append(finding('metric_definition_unapproved','review','Metric definition needs approval',
            'No totals were calculated because the supplied metric definition version is not approved.'))
    if preflight_holds:
        return result(SPEC['id'],'Source readiness checks require review.',
            {'matched_records':0},preflight_holds,answer_status='withheld',source_snapshot=snapshot,table=[])
    records=rows(data['records'],minimum=1);unique(records)
    currencies=set();regions=set();products=set()
    for row in records:
        obj(row,['id','date','region','product','currency','revenue','refund','cost','units'])
        text(row['id'],limit=128);record_date=day(row['date'])
        if not coverage_start<=record_date<=coverage_end:
            raise InputError('A record date falls outside the declared snapshot coverage')
        for field in ('region','product','currency'):
            text(row[field],field,100)
        if len(row['currency'])!=3 or (not row['currency'].isascii() or not row['currency'].isalpha()) or row['currency']!=row['currency'].upper():
            raise InputError('Currency must be a three-letter uppercase code')
        for field in ('revenue','refund','cost'):
            if money(row[field])<0:
                raise InputError('Revenue, refunds and cost cannot be negative')
        integer(row['units'],'units')
        currencies.add(row['currency']);regions.add(row['region']);products.add(row['product'])
    plan=ai.ask(PROMPT,{'question':question,'as_of':as_of.isoformat(),
        'coverage':{'start':coverage_start.isoformat(),'end':coverage_end.isoformat(),
                    'data_as_of':data_as_of.isoformat()},
        'currencies':sorted(currencies),'regions':sorted(regions),'products':sorted(products)},PLAN)
    if not plan['question_quote'].strip() or plan['question_quote'] not in question:
        raise InputError('Analysis plan must quote the actual business question')
    if plan['status']=='clarify':
        text(plan['clarification'],'clarification')
        return result(SPEC['id'],'A business definition needs clarification.',{'matched_records':0},
            [finding('clarification','review','Clarify the question',plan['clarification'])],
            answer_status='withheld',source_snapshot=snapshot,plan=plan,table=[])
    if plan['clarification']:
        raise InputError('A ready plan cannot contain unresolved clarification')
    start=day(plan['start_date']) if plan['start_date'] else None
    end=day(plan['end_date']) if plan['end_date'] else None
    if start and end and start>end:
        raise InputError('Analysis start date exceeds end date')
    effective_start=start or coverage_start
    effective_end=end or coverage_end
    if (start and (start<coverage_start or start>coverage_end)) or (end and (end<coverage_start or end>coverage_end)):
        return result(SPEC['id'],'The requested period exceeds the complete source coverage.',
            {'matched_records':0},[finding('snapshot_coverage','review','Requested period is not fully covered',
            f"The complete snapshot covers {coverage_start.isoformat()} through {coverage_end.isoformat()}; no partial total was calculated.")],
            answer_status='withheld',source_snapshot=snapshot,plan=plan,table=[])
    if effective_start>effective_end:
        raise InputError('Analysis start date exceeds end date')
    start=effective_start
    end=effective_end
    currency=plan['currency']
    if not currency and len(currencies)>1 and plan['measure']!='units':
        return result(SPEC['id'],'Choose a reporting currency before combining amounts.',
            {'matched_records':0},[finding('mixed_currency','review','Multiple currencies',
            'Currency conversion is not configured. Select one currency.')],
            answer_status='withheld',source_snapshot=snapshot,plan=plan,table=[])
    currency=currency or ('' if plan['measure']=='units' else next(iter(currencies)))
    if (currency and currency not in currencies) or set(plan['regions'])-regions or set(plan['products'])-products:
        return result(SPEC['id'],'The requested filters are not present in this dataset.',
            {'matched_records':0},[finding('unknown_filter','review','Check the source data',
            'No answer was inferred for an unknown currency, product or region.')],
            answer_status='withheld',source_snapshot=snapshot,plan=plan,table=[])
    groups=defaultdict(lambda:{'value':Decimal(0),'records':[]})
    matched=[]
    for row in records:
        d=day(row['date'])
        if (start and d<start) or (end and d>end) or (currency and row['currency']!=currency):
            continue
        if plan['regions'] and row['region'] not in plan['regions']:
            continue
        if plan['products'] and row['product'] not in plan['products']:
            continue
        key=(row['date'][:7] if plan['group_by']=='month' else row.get(plan['group_by'],'All records'))
        values={'revenue':money(row['revenue']),'net_revenue':money(row['revenue'])-money(row['refund']),
                'cost':money(row['cost']),'gross_profit':money(row['revenue'])-money(row['refund'])-money(row['cost']),
                'units':Decimal(row['units'])}
        groups[key]['value']+=values[plan['measure']];groups[key]['records'].append(row['id']);matched.append(row['id'])
    table=[{'group':key,'value':str(v['value']),'record_ids':v['records']} for key,v in sorted(groups.items())]
    findings=[]
    if not matched:
        findings.append(finding('no_data','review','No matching records','An empty snapshot is not evidence of zero business activity.'))
    total=sum((v['value'] for v in groups.values()),Decimal(0))
    return result(SPEC['id'],f"{plan['measure'].replace('_',' ').capitalize()} across {len(matched)} matching records in the covered period.",
        {'matched_records':len(matched),'groups':len(table),'total':str(total) if matched else None,'unit':'units' if plan['measure']=='units' else currency},
        findings,plan=plan,table=table,
        source_snapshot=snapshot,
        coverage={'start':coverage_start.isoformat(),'end':coverage_end.isoformat()},
        answer_status='calculated' if matched else 'withheld',
        calculation={'revenue':'sum(revenue)','net_revenue':'sum(revenue - refund)','cost':'sum(cost)',
                     'gross_profit':'sum(revenue - refund - cost)','units':'sum(units)'}[plan['measure']])
