"""Version-aware RFP answer matrix with conservative evidence status handling."""
from enterprise_ai.common import (InputError, obj, text, day, rows, unique, object_schema,
    array_schema, string_schema, EVIDENCE_SCHEMA, evidence, finding, result)

SPEC = {'id': 'proposal-operations', 'title': 'Proposal Evidence Workbench',
        'category': 'RFP assistance', 'summary': 'Review RFP answers against approved, dated product evidence and unresolved contradictions.'}
SCHEMA = object_schema({'answers': array_schema(object_schema({
    'requirement_id': string_schema(), 'status': string_schema(['supported', 'gap', 'conflict']),
    'draft': string_schema(), 'evidence': EVIDENCE_SCHEMA}))})


def run(data, ai):
    obj(data, ['as_of', 'requirements', 'sources'])
    today = day(data['as_of'])
    requirements = rows(data['requirements'], 'requirements', 100, 1)
    for item in requirements:
        obj(item, ['id', 'text']); text(item['text'])
    reqs = unique(requirements)
    source_rows = rows(data['sources'], 'sources', 100)
    validity = {}
    for source in source_rows:
        obj(source, ['id', 'text', 'valid_from', 'valid_until', 'approval'])
        text(source['text']); start = day(source['valid_from']); end = day(source['valid_until'])
        if start > end: raise InputError('Source validity period is reversed')
        if source['approval'] not in ('approved', 'draft'):
            raise InputError('Unknown evidence approval')
        validity[text(source['id'], 'source id', 128)] = ('draft' if source['approval'] == 'draft' else
            'not_yet_valid' if today < start else 'expired' if today > end else 'current')
    sources = unique(source_rows)
    answer = ai.ask('Return exactly one answer for every requirement. Use supplied sources only. Identify missing evidence and contradictions, including version differences. Supported needs direct evidence; gap must have empty draft and evidence. Conflict needs evidence from at least two sources and no draft. Draft answers are for human review, never declarations of compliance. Quote exact source text.', data, SCHEMA)
    answers = rows(answer['answers'], 'answers', 100)
    mapped = unique(answers, 'requirement_id')
    if set(mapped) != set(reqs): raise InputError('Every requirement requires exactly one answer')
    findings = []; matrix = []
    for rid in reqs:
        item = mapped[rid]; ev = evidence(item['evidence'], {sid: s['text'] for sid, s in sources.items()})
        cited = {e['source_id'] for e in ev}; status = item['status']
        if item['draft']:
            text(item['draft'], 'draft', 10000)
        if status == 'supported' and (not ev or not item['draft'].strip()):
            raise InputError('Supported answer requires evidence and a draft')
        if status == 'gap' and (ev or item['draft']): raise InputError('Evidence gap must not contain an unsupported draft')
        if status == 'conflict' and (len(cited) < 2 or item['draft']):
            raise InputError('Conflict requires two sources and no affirmative draft')
        invalid = {sid: validity[sid] for sid in sorted(cited) if validity[sid] != 'current'}
        if status == 'supported' and invalid: status = 'evidence_review'
        draft = item['draft'] if status == 'supported' else ''
        if status != 'supported':
            findings.append(finding(status, 'review', 'Requirement needs evidence review',
                                    rid + ': ' + status, sorted(cited)))
        matrix.append({'requirement_id': rid, 'requirement': reqs[rid]['text'], 'status': status,
                       'draft': draft, 'evidence': ev, 'invalid_sources': invalid,
                       'review_status': 'unreviewed'})
    unresolved = sum(m['status'] != 'supported' for m in matrix)
    return result(SPEC['id'], 'Draft response matrix; no answer is approved or submitted.',
                  {'requirements': len(matrix), 'draftable': len(matrix) - unresolved, 'unresolved': unresolved},
                  findings, [{'action': 'review_requirement', 'requirement_id': m['requirement_id'],
                              'priority': 'evidence_first' if m['status'] != 'supported' else 'verify_draft'} for m in matrix],
                  matrix=matrix, source_validity=validity)
