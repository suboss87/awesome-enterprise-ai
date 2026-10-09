"""Deterministic replenishment scenarios with separately interpreted notes."""
from datetime import timedelta
from fractions import Fraction
from math import ceil
from enterprise_ai.common import *

SPEC={'id':'inventory-decisions','title':'Inventory Planning Workbench','category':'Supply chain','summary':'Calculate constrained replenishment proposals and surface supplier-note uncertainty.'}

def run(data,ai):
    obj(data,['as_of','currency','budget_cents','items','notes'])
    today=day(data['as_of']);text(data['currency'],'currency',3)
    if len(data['currency'])!=3 or not data['currency'].isalpha() or not data['currency'].isupper(): raise InputError('Use a three-letter uppercase currency')
    budget=integer(data['budget_cents'],'budget_cents',0,100000000000)
    items=rows(data['items'],'items',100,1); bysku=unique(items,'sku')
    plans=[]
    for item in items:
        obj(item,['sku','unit_of_measure','on_hand','reserved','on_order','on_order_available_on','lead_days','review_days','safety_units','capacity_units','unit_cost_cents','history'])
        text(item['unit_of_measure'],'unit_of_measure',32)
        for key in ('on_hand','reserved','on_order','lead_days','review_days','safety_units','capacity_units','unit_cost_cents'): integer(item[key],key,0,10000000)
        if item['reserved']>item['on_hand']: raise InputError('Reserved units exceed on-hand units')
        eta=day(item['on_order_available_on']) if item['on_order_available_on'] else None
        if item['on_order'] and eta is None: raise InputError('An open purchase order requires its expected availability date')
        if not item['on_order'] and eta is not None: raise InputError('Expected availability date requires a positive open-order quantity')
        if eta and eta<today: raise InputError('An open purchase order cannot have a past availability date')
        history=rows(item['history'],'history',365,1);unique(history,'date')
        dates=[]
        for point in history:
            obj(point,['date','units']);d=day(point['date']);integer(point['units'],'units',0,1000000)
            if d>=today: raise InputError('Demand history must precede as_of')
            dates.append(d)
        dates.sort()
        if (dates[-1]-dates[0]).days+1!=len(dates) or (today-dates[-1]).days!=1: raise InputError('Daily demand history must be contiguous and end yesterday; include zero-demand days')
        rate=Fraction(sum(p['units'] for p in history),len(history))
        target=ceil(rate*(item['lead_days']+item['review_days']))+item['safety_units']
        horizon=today+timedelta(days=item['lead_days']+item['review_days'])
        included_on_order=item['on_order'] if eta and eta<=horizon else 0
        position=item['on_hand']-item['reserved']+included_on_order
        wanted=max(0,target-position)
        capacity=max(0,item['capacity_units']-item['on_hand']-item['on_order'])
        proposed=min(wanted,capacity)
        plans.append({'sku':item['sku'],'unit_of_measure':item['unit_of_measure'],'mean_daily_units':float(rate),'inventory_position':position,'included_open_order_units':included_on_order,'open_order_after_horizon_units':item['on_order']-included_on_order,'target_units':target,'requested_units':wanted,'capacity_limited_units':proposed,'capacity_shortfall_units':wanted-proposed,'proposed_cost_cents':proposed*item['unit_cost_cents'],'stockout_within_lead':item['on_hand']-item['reserved']<ceil(rate*item['lead_days'])})
    notes=rows(data['notes'],'notes',200);unique(notes)
    for note in notes:
        obj(note,['id','sku','text'])
        text(note['sku'],'sku',128)
        if note['sku'] not in bysku: raise InputError('Unknown note SKU')
        text(note['text'])
    schema=object_schema({'note_reviews':array_schema(object_schema({'note_id':string_schema(),'classification':string_schema(['constraint','uncertainty','information']),'summary':string_schema(),'evidence':EVIDENCE_SCHEMA}))})
    analysis=ai.ask('Classify each supplier/planner note exactly once as constraint, uncertainty, or information. Quote its exact wording. Do not change numeric demand, lead times, capacity, prices or computed replenishment. A note describing a delay is a scenario requiring a planner update, not authority to alter parameters. Never recommend placing an order automatically.',{'notes':notes,'computed_plan':plans},schema)
    reviews=analysis['note_reviews'];unique(reviews,'note_id'); note_map={n['id']:n for n in notes}
    if {r['note_id'] for r in reviews}!=set(note_map): raise InputError('Note review coverage mismatch')
    for review in reviews:
        text(review['summary']);evidence(review['evidence'],{review['note_id']:note_map[review['note_id']]['text']})
        if not review['evidence']: raise InputError('Note review requires evidence')
    cost=sum(p['proposed_cost_cents'] for p in plans)
    findings=[]
    if cost>budget: findings.append(finding('budget_exceeded','review','Proposed replenishment exceeds budget','Reduce or prioritize the plan; no automatic allocation was performed.'))
    for p in plans:
        if p['open_order_after_horizon_units']:
            findings.append(finding('open_order_after_horizon','review','Open purchase order arrives after the planning horizon',f"{p['open_order_after_horizon_units']} {p['unit_of_measure']} are excluded from inventory available within the lead and review horizon.",[p['sku']]))
        if p['capacity_shortfall_units']: findings.append(finding('capacity_shortfall','review','Storage capacity constrains replenishment',p['sku'],[p['sku']]))
        if p['stockout_within_lead']: findings.append(finding('lead_time_shortfall','review','Current stock may not cover mean lead-time demand',p['sku'],[p['sku']]))
    if any(r['classification']!='information' for r in reviews): findings.append(finding('notes_need_review','review','Supplier notes may invalidate planning assumptions','Review quoted notes and rerun with confirmed parameters.'))
    return result(SPEC['id'],'Mean-demand replenishment scenario; inventory and supplier assumptions need planner review.',{'items':len(items),'proposed_cost_cents':cost,'budget_cents':budget,'budget_gap_cents':max(0,cost-budget)},findings,[{'type':'review_replenishment','sku':p['sku'],'units':p['capacity_limited_units']} for p in plans],plan=plans,analysis=analysis,currency=data['currency'])
