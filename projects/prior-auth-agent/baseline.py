"""Rules-only baseline: a keyword table per criterion and date regexes over the structured fields and documents.

This is what a utilization management team builds without a model: the structured
request fields drive eligibility, codes, site and the clock; therapy visits are dated
lines that start with an ISO or US numeric date; BMI and HbA1c come from fixed value
patterns; presence criteria match a keyword table the team maintains per policy.
Visit dates written out in prose and faxed pages with OCR noise produce no match, so
those requests come out as missing documentation. Embedded instructions are
invisible to it. The same `criteria.py` rules evaluate the evidence and decide the route.
"""
import importlib.util
import re
from datetime import datetime
from pathlib import Path

from enterprise_ai.common import InputError

_here = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('prior_auth_criteria_b', _here/'criteria.py')
rules = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rules)
_aspec = importlib.util.spec_from_file_location('prior_auth_agent_b', _here/'agent.py')
agent_module = importlib.util.module_from_spec(_aspec)
_aspec.loader.exec_module(agent_module)

KEYWORDS = {   # presence and exclusion criteria: the line that documents them
    'LS-2': r'straight-leg raise|radicul|reflex',
    'LS-3': r'XR LUMBAR SPINE',
    'LS-4': r'\bno (?:pacemaker|implanted)',
    'LS-5': r'laminectomy|discitis|osteomyelitis|metasta',
    'BS-3': r'psychologically cleared',
    'CG-2': r'\binsulin (?:glargine|lispro|aspart|degludec|detemir|pump)',
    'CG-3': r'glycemic control',
}
VALUES = {'bmi': r'\bBMI\s+(\d{2}\.\d)\b', 'hba1c': r'Hemoglobin A1c\s+(\d{1,2}\.\d)\b'}
VISIT = re.compile(r'^\s*(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\s')


def _iso(raw):
    return raw if '-' in raw else datetime.strptime(raw, '%m/%d/%Y').date().isoformat()


def read_criterion(criterion, documents):
    """The baseline's evidence record for one criterion, or None."""
    params, kind = criterion['params'], criterion['kind']
    docs = [d for d in documents if d['kind'] in params.get('evidence_kinds', [])]
    quotes, values = [], []
    for doc in docs:
        for line in doc['text'].splitlines():
            if kind == 'duration':
                m = VISIT.match(line)
                if m:
                    quotes.append({'source_id': doc['id'], 'quote': line.strip(), 'date': _iso(m.group(1))})
            elif kind == 'threshold':
                m = re.search(VALUES[params['value_name']], line)
                if m:
                    quotes.append({'source_id': doc['id'], 'quote': line.strip(), 'date': doc['date']})
                    values.append({'name': params['value_name'], 'value': float(m.group(1)), 'source_id': doc['id'], 'date': doc['date']})
            elif criterion['id'] in KEYWORDS and re.search(KEYWORDS[criterion['id']], line, re.I):
                quotes.append({'source_id': doc['id'], 'quote': line.strip(), 'date': doc['date']})
    if not quotes:
        return None
    return {'criterion_id': criterion['id'], 'met_claim': kind in ('presence', 'exclusion'), 'quotes': quotes, 'values': values}


def run(data):
    agent_module.validate(data)
    records = {}
    for criterion in data['coverage_policy']['criteria']:
        if criterion['kind'] == 'code_pairing':
            continue
        raw = read_criterion(criterion, data['documents'])
        if raw is None:
            continue
        try:
            records[criterion['id']] = rules.normalize_record(data, raw)
        except InputError:
            continue
    verdict = rules.assess(data, records)
    output = rules.build_output(data, verdict, None, [], 'keyword-baseline')
    output['baseline'] = 'keyword-and-date-regex'
    return output
