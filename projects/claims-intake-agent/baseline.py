"""Rules-only baseline: header-keyword classification and key-value regex extraction per template.

This is what an intake team gets from a forms-based capture tool: the structured
FNOL form, police report, estimate and registration parse well; a call transcript
or free prose does not. Notes about prior damage, pressure or embedded
instructions are invisible to it. The same `intake.py` rules decide the route.
"""
import importlib.util
import re
from pathlib import Path

_here = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('claims_intake_rules_b', _here/'intake.py')
intake = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(intake)
_aspec = importlib.util.spec_from_file_location('claims_agent_b', _here/'agent.py')
agent_module = importlib.util.module_from_spec(_aspec)
_aspec.loader.exec_module(agent_module)


def _first(pattern, text, default=''):
    m = re.search(pattern, text, re.I | re.M)
    return m.group(1).strip() if m else default


def classify(text):
    head = text[:200].upper()
    if 'FIRST NOTICE OF LOSS' in head:
        return 'fnol_form'
    if 'INCIDENT REPORT' in head:
        return 'police_report'
    if 'REPAIR ESTIMATE' in head:
        return 'repair_estimate'
    if head.startswith('PHOTO SET'):
        return 'photo_notes'
    if 'REGISTRATION CERTIFICATE' in head:
        return 'registration'
    if 'CALL TRANSCRIPT' in head:
        return 'fnol_form'
    return 'other'


def empty():
    return {'claimant_name': '', 'policy_number': '', 'incident_date': '', 'incident_location': '', 'vin': '', 'plate': '', 'loss_type': '',
            'damage_area': '', 'third_party_or_injury': False, 'police_report_filed': False, 'estimate_total': 0, 'report_number': '', 'notes': ''}


def extract(doc):
    text = doc['text']
    kind = classify(text)
    f = empty()
    if kind == 'fnol_form' and 'FIRST NOTICE OF LOSS' in text[:60].upper():
        f.update({'policy_number': _first(r'^Policy number:\s*(.+)$', text), 'claimant_name': _first(r'^Claimant:\s*(.+)$', text),
                  'incident_date': _first(r'^Date of loss:\s*(\d{4}-\d{2}-\d{2})', text), 'incident_location': _first(r'^Location:\s*(.+)$', text),
                  'vin': _first(r'^VIN:\s*([A-Z0-9]{17})', text), 'plate': _first(r'^Plate:\s*(.+)$', text),
                  'loss_type': _first(r'^Loss type:\s*(\w+)', text).lower(), 'damage_area': _first(r'^Damage reported:\s*(\w+)', text),
                  'third_party_or_injury': _first(r'^Third party involved:\s*(\w+)', text).lower() == 'yes' or _first(r'^Injuries:\s*(\w+)', text).lower() == 'yes',
                  'police_report_filed': _first(r'^Police report filed:\s*(\w+)', text).lower() == 'yes'})
    elif kind == 'fnol_form':   # call transcript: only the policy number is reliably parseable by regex
        f.update({'policy_number': _first(r'policy\s+(PA-\d{4}-\d{5})', text), 'claimant_name': _first(r'identified as ([A-Z][a-z]+ [A-Z][a-z]+)', text),
                  'vin': _first(r'full VIN is ([A-Z0-9]{17})', text), 'plate': _first(r'\(plate ([A-Z0-9]{4} [A-Z]{3})\)', text),
                  'loss_type': _first(r'as a (\w+) loss', text).lower(), 'damage_area': _first(r'damage to the (\w+)', text),
                  'third_party_or_injury': 'Another vehicle was involved' in text or 'Someone was hurt' in text,
                  'police_report_filed': 'I have a report' in text})
    elif kind == 'police_report':
        f.update({'report_number': _first(r'^Report No:\s*(.+)$', text), 'incident_date': _first(r'^Date of incident:\s*(\d{4}-\d{2}-\d{2})', text),
                  'incident_location': _first(r'^Location:\s*(.+)$', text), 'vin': _first(r'VIN ([A-Z0-9]{17})', text),
                  'plate': _first(r'plate ([A-Z0-9]{4} [A-Z]{3})', text), 'claimant_name': _first(r'^Driver 1:\s*(.+)$', text)})
    elif kind == 'repair_estimate':
        f.update({'vin': _first(r'^VIN:\s*([A-Z0-9]{17})', text), 'plate': _first(r'^Plate:\s*(.+)$', text),
                  'estimate_total': float(_first(r'^Estimate total:\s*\$([\d,]+\.\d{2})', text, '0').replace(',', '') or 0)})
    elif kind == 'registration':
        f.update({'vin': _first(r'^VIN:\s*([A-Z0-9]{17})', text), 'plate': _first(r'^Registration mark:\s*(.+)$', text),
                  'claimant_name': _first(r'^Registered keeper:\s*(.+)$', text)})
    elif kind == 'photo_notes':
        m = re.search(r'wide shot of the (\w+) of the vehicle', text)
        f['damage_area'] = m.group(1) if m else ''
    return {'document_id': doc['id'], 'document_type': kind, 'fields': f}


def run(data):
    claim, policies = agent_module.validate(data)
    extractions = [extract(doc) for doc in claim['documents']]
    verdict = intake.assess(extractions, policies, data['as_of'])
    output = intake.build_output(extractions, verdict, None, [], [d['id'] for d in claim['documents']])
    output['baseline'] = 'forms-capture-regex'
    return output
