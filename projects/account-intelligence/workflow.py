"""CRM review with sourced meeting changes; no fabricated forecast values."""
from enterprise_ai.common import (InputError, obj, text, integer, day, rows, unique,
    object_schema, array_schema, string_schema, EVIDENCE_SCHEMA, evidence, finding, result)

SPEC = {'id': 'account-intelligence', 'title': 'Account Review Workbench',
        'category': 'Sales intelligence', 'summary': 'Reconcile CRM opportunities with meeting commitments and surface reviewable changes.'}
SCHEMA = object_schema({'observations': array_schema(object_schema({
    'opportunity_id': string_schema(), 'kind': string_schema(['blocker', 'next_step', 'date_change']),
    'proposed_date': string_schema(), 'evidence': EVIDENCE_SCHEMA}))})


def run(data, ai):
    obj(data, ['as_of', 'account', 'opportunities', 'meetings'])
    today = day(data['as_of']); account = obj(data['account'], ['id', 'name'])
    text(account['id'], 'account id', 128); text(account['name'], 'account name', 256)
    opportunities = rows(data['opportunities'], 'opportunities', 100)
    for op in opportunities:
        obj(op, ['id', 'account_id', 'title', 'amount_cents', 'stage', 'close_date', 'next_step'])
        text(op['title'], 'title', 256); integer(op['amount_cents'])
        if op['account_id'] != account['id']: raise InputError('Cross-account opportunity rejected')
        if op['stage'] not in ('prospect', 'qualified', 'proposal', 'won', 'lost'): raise InputError('Unknown stage')
        day(op['close_date'])
        if not isinstance(op['next_step'], str): raise InputError('next_step must be text, empty if missing')
        if op['next_step']: text(op['next_step'])
    ops = unique(opportunities)
    meetings = rows(data['meetings'], 'meetings', 100)
    for meeting in meetings:
        obj(meeting, ['id', 'account_id', 'date', 'text'])
        text(meeting['text'])
        if meeting['account_id'] != account['id']: raise InputError('Cross-account meeting rejected')
        if day(meeting['date']) > today: raise InputError('Future meeting is not an observed event')
    sources = unique(meetings)
    answer = ai.ask('Extract meeting statements relevant to supplied opportunity IDs. Return blockers, next steps, and proposed close-date changes. Each needs an exact meeting quote. For a date change, proposed_date must be an ISO date appearing literally in a supporting quote; otherwise omit the date-change observation. All other proposed_date values must be empty. Do not infer deal values, probability, buyer names, or completion from plans. Do not duplicate observations.', data, SCHEMA)
    findings = []; observations = []; seen = set()
    for item in rows(answer['observations'], 'observations', 200):
        oid = item['opportunity_id']
        if oid not in ops: raise InputError('Unknown opportunity in observation')
        ev = evidence(item['evidence'], {sid: s['text'] for sid, s in sources.items()})
        if not ev: raise InputError('Meeting observation requires evidence')
        key = (oid, item['kind'], tuple(sorted((e['source_id'], e['quote']) for e in ev)))
        if key in seen: raise InputError('Duplicate observation')
        seen.add(key)
        if item['kind'] == 'date_change':
            proposed = day(item['proposed_date'])
            if not any(proposed.isoformat() in e['quote'] for e in ev): raise InputError('Proposed date is not quoted')
            if proposed.isoformat() != ops[oid]['close_date']:
                findings.append(finding('close_date_conflict', 'review', 'Meeting date differs from CRM',
                    oid + ': CRM ' + ops[oid]['close_date'] + '; meeting ' + proposed.isoformat(), [e['source_id'] for e in ev]))
        elif item['proposed_date'] != '': raise InputError('Only a date change may propose a date')
        observations.append({**item, 'review_status': 'unreviewed', 'crm_changed': False})
    active = [o for o in opportunities if o['stage'] not in ('won', 'lost')]
    for op in active:
        if day(op['close_date']) < today:
            findings.append(finding('overdue_close', 'review', 'Open opportunity past close date', op['id'], [op['id']]))
        if not op['next_step'].strip():
            findings.append(finding('missing_next_step', 'review', 'CRM next step missing', op['id'], [op['id']]))
    latest = max((day(m['date']) for m in meetings), default=None)
    if latest is None or (today - latest).days > 30:
        findings.append(finding('stale_engagement', 'review', 'No recent meeting recorded', 'No supplied meeting within 30 days.'))
    return result(SPEC['id'], 'Account review uses recorded CRM values and quoted meeting statements.',
                  {'open_pipeline_cents': sum(o['amount_cents'] for o in active), 'active_opportunities': len(active),
                   'meeting_observations': len(observations)}, findings,
                  [{'action': 'review_meeting_observation', 'opportunity_id': o['opportunity_id'], 'kind': o['kind']} for o in observations],
                  account=account, opportunities=opportunities, observations=observations,
                  latest_meeting_date=latest.isoformat() if latest else None,
                  forecast_probability=None)
