"""Natural-language business analysis with an allowlisted plan and exact arithmetic."""
from collections import defaultdict
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
PROMPT='''Translate the question into this supported analysis plan only. Revenue means gross revenue; net_revenue subtracts refunds; gross_profit subtracts refunds and cost. Units are recorded units, not net of returns. Group by none, region, product or calendar month. Dates are inclusive; empty date means unbounded. Use the supplied as_of for relative dates. Return exact region/product values. If unsupported measures, unclear business meaning or incompatible requested dimensions prevent an answer, status=clarify with a precise question. Never substitute a supported metric for unsupported profit margin, growth, average or forecast. Do not choose a currency for the user if several exist. Empty currency means unspecified. Quote the exact part of the user question that defines the requested analysis. No SQL or code execution.'''


def run(data,ai):
    obj(data,['question','as_of','records'])
    question=text(data['question']);as_of=day(data['as_of'])
    records=rows(data['records'],minimum=1);unique(records)
    currencies=set();regions=set();products=set()
    for row in records:
        obj(row,['id','date','region','product','currency','revenue','refund','cost','units'])
        text(row['id'],limit=128);day(row['date'])
        for field in ('region','product','currency'):
            text(row[field],field,100)
        if len(row['currency'])!=3 or not row['currency'].isalpha() or row['currency']!=row['currency'].upper():
            raise InputError('Currency must be a three-letter uppercase code')
        for field in ('revenue','refund','cost'):
            if money(row[field])<0:
                raise InputError('Revenue, refunds and cost cannot be negative')
        integer(row['units'],'units')
        currencies.add(row['currency']);regions.add(row['region']);products.add(row['product'])
    plan=ai.ask(PROMPT,{'question':question,'as_of':as_of.isoformat(),
        'currencies':sorted(currencies),'regions':sorted(regions),'products':sorted(products)},PLAN)
    if not plan['question_quote'].strip() or plan['question_quote'] not in question:
        raise InputError('Analysis plan must quote the actual business question')
    if plan['status']=='clarify':
        text(plan['clarification'],'clarification')
        return result(SPEC['id'],'A business definition needs clarification.',{'matched_records':0},
            [finding('clarification','review','Clarify the question',plan['clarification'])],
            answer_status='withheld',plan=plan,table=[])
    if plan['clarification']:
        raise InputError('A ready plan cannot contain unresolved clarification')
    start=day(plan['start_date']) if plan['start_date'] else None
    end=day(plan['end_date']) if plan['end_date'] else None
    if start and end and start>end:
        raise InputError('Analysis start date exceeds end date')
    currency=plan['currency']
    if not currency and len(currencies)>1 and plan['measure']!='units':
        return result(SPEC['id'],'Choose a reporting currency before combining amounts.',
            {'matched_records':0},[finding('mixed_currency','review','Multiple currencies',
            'Currency conversion is not configured. Select one currency.')],
            answer_status='withheld',plan=plan,table=[])
    currency=currency or ('' if plan['measure']=='units' else next(iter(currencies)))
    if (currency and currency not in currencies) or set(plan['regions'])-regions or set(plan['products'])-products:
        return result(SPEC['id'],'The requested filters are not present in this dataset.',
            {'matched_records':0},[finding('unknown_filter','review','Check the source data',
            'No answer was inferred for an unknown currency, product or region.')],
            answer_status='withheld',plan=plan,table=[])
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
    return result(SPEC['id'],f"{plan['measure'].replace('_',' ').capitalize()} across {len(matched)} matching records.",
        {'matched_records':len(matched),'groups':len(table),'total':str(total) if matched else None,'unit':'units' if plan['measure']=='units' else currency},
        findings,plan=plan,table=table,
        answer_status='calculated' if matched else 'withheld',
        calculation={'revenue':'sum(revenue)','net_revenue':'sum(revenue - refund)','cost':'sum(cost)',
                     'gross_profit':'sum(revenue - refund - cost)','units':'sum(units)'}[plan['measure']])
