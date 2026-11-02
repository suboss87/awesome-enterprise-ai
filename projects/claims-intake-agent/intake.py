"""Deterministic claims-intake rules: policy binding, completeness, conflict arbitration, triage.

The model reads each document in the packet and extracts fields per document.
This module merges them with a source-authority table, checks the packet against
the coverage's required documents, and decides the triage route. The agent and the
baseline both call these functions.
"""
import re
from datetime import date, timedelta

from enterprise_ai.common import InputError

ROUTES = ('ready_for_adjuster', 'missing_information', 'conflicts_for_adjuster', 'coverage_question', 'not_a_claim_packet')
LOSS_TYPES = ('collision', 'theft', 'glass', 'weather', 'vandalism', 'other')
DOC_TYPES = ('fnol_form', 'police_report', 'repair_estimate', 'photo_notes', 'registration', 'other')

# Required documents by loss type. (document type, condition) where condition is None or a field name of the FNOL.
REQUIRED = {
    'collision': [('fnol_form', None), ('repair_estimate', None), ('photo_notes', None), ('police_report', 'third_party_or_injury')],
    'theft': [('fnol_form', None), ('police_report', None), ('registration', None)],
    'glass': [('fnol_form', None), ('repair_estimate', None)],
    'weather': [('fnol_form', None), ('repair_estimate', None), ('photo_notes', None)],
    'vandalism': [('fnol_form', None), ('police_report', None), ('repair_estimate', None), ('photo_notes', None)],
    'other': [('fnol_form', None)],
}

# Which source wins a disagreement, per field. First listed wins.
AUTHORITY = {
    'incident_date': ['police_report', 'fnol_form', 'repair_estimate'],
    'incident_location': ['police_report', 'fnol_form'],
    'vin': ['registration', 'fnol_form', 'repair_estimate'],
    'plate': ['registration', 'police_report', 'fnol_form', 'repair_estimate'],
    'claimant_name': ['fnol_form', 'police_report', 'repair_estimate'],
    'damage_area': ['photo_notes', 'repair_estimate', 'fnol_form'],
}
TOLERANCE_DAYS = 1
FLAG_ORDER = ['NOT_A_CLAIM_PACKET', 'POLICY_NOT_FOUND', 'POLICY_INACTIVE_ON_LOSS_DATE', 'VEHICLE_NOT_ON_POLICY', 'DRIVER_NOT_LISTED',
              'COVERAGE_NOT_HELD', 'MISSING_DOCUMENT', 'DATE_CONFLICT', 'VIN_CONFLICT', 'PLATE_CONFLICT', 'NAME_CONFLICT', 'LOCATION_CONFLICT',
              'DAMAGE_AREA_CONFLICT', 'ESTIMATE_EXCEEDS_VALUE', 'ESTIMATE_GAP', 'PRE_EXISTING_DAMAGE', 'PROMPT_INJECTION', 'SUSPICIOUS_REQUEST']
MODEL_ONLY_FLAGS = {'PROMPT_INJECTION', 'SUSPICIOUS_REQUEST', 'PRE_EXISTING_DAMAGE'}

FIELD_SCHEMA = {'type': 'object', 'properties': {
    'claimant_name': {'type': 'string'}, 'policy_number': {'type': 'string'}, 'incident_date': {'type': 'string', 'description': 'YYYY-MM-DD or empty'},
    'incident_location': {'type': 'string'}, 'vin': {'type': 'string'}, 'plate': {'type': 'string'},
    'loss_type': {'type': 'string', 'enum': list(LOSS_TYPES) + ['']},
    'damage_area': {'type': 'string', 'description': 'front, rear, left, right, roof, glass, interior, multiple or empty'},
    'third_party_or_injury': {'type': 'boolean'}, 'police_report_filed': {'type': 'boolean'},
    'estimate_total': {'type': 'number', 'description': '0 when not an estimate'},
    'report_number': {'type': 'string'}, 'notes': {'type': 'string', 'description': 'pre-existing damage, inconsistencies, anything an adjuster must know'}}}

EXTRACTION_SCHEMA = {'type': 'object', 'properties': {
    'document_id': {'type': 'string'}, 'document_type': {'type': 'string', 'enum': list(DOC_TYPES)}, 'fields': FIELD_SCHEMA}}


def parse_date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def norm(value):
    return re.sub(r'[^a-z0-9]', '', str(value or '').lower())


def norm_vin(value):
    return re.sub(r'[^A-Z0-9]', '', str(value or '').upper())


def vin_near(a, b):
    """Equal after the common OCR confusions 0/O, 1/I, 5/S, 8/B."""
    table = str.maketrans('OISB', '0158')
    return norm_vin(a).translate(table) == norm_vin(b).translate(table)


def name_similar(a, b):
    """Same person: identical tokens, or same last name with the same first initial."""
    ta, tb = re.findall(r'[a-z]+', str(a).lower()), re.findall(r'[a-z]+', str(b).lower())
    if not ta or not tb:
        return True
    if set(ta) == set(tb):
        return True
    return ta[-1] == tb[-1] and ta[0][0] == tb[0][0]


def find_policy(policies, number):
    number = norm(number)
    for policy in policies:
        if norm(policy['policy_number']) == number:
            return policy
    return None


def merge(extractions):
    """Per-field winner by source authority, plus conflicts. Returns (claim, conflicts)."""
    by_type = {}
    for ext in extractions:
        by_type.setdefault(ext['document_type'], []).append(ext)
    claim, conflicts = {}, []
    for field, order in AUTHORITY.items():
        values = []
        for doc_type in order:
            for ext in by_type.get(doc_type, []):
                value = ext['fields'].get(field, '')
                if value not in ('', None):
                    values.append((doc_type, ext['document_id'], value))
        if not values:
            continue
        claim[field] = values[0][2]
        for doc_type, doc_id, value in values[1:]:
            if not _agree(field, values[0][2], value):
                conflicts.append({'field': field, 'winner': {'source': values[0][0], 'document_id': values[0][1], 'value': values[0][2]},
                                  'other': {'source': doc_type, 'document_id': doc_id, 'value': value}})
    fnol = (by_type.get('fnol_form') or [{}])[0]
    fields = fnol.get('fields', {}) if fnol else {}
    for key in ('policy_number', 'loss_type', 'third_party_or_injury', 'police_report_filed'):
        if fields.get(key) not in ('', None):
            claim[key] = fields[key]
    for ext in extractions:
        if ext['document_type'] == 'repair_estimate' and ext['fields'].get('estimate_total'):
            claim.setdefault('estimates', []).append({'document_id': ext['document_id'], 'total': ext['fields']['estimate_total']})
        if ext['document_type'] == 'police_report' and ext['fields'].get('report_number'):
            claim['report_number'] = ext['fields']['report_number']
    return claim, conflicts


def _agree(field, a, b):
    if field == 'incident_date':
        da, db = parse_date(a), parse_date(b)
        return da is None or db is None or abs((da - db).days) <= TOLERANCE_DAYS
    if field == 'vin':
        return vin_near(a, b)
    if field == 'plate':
        return norm_vin(a) == norm_vin(b)
    if field == 'claimant_name':
        return name_similar(a, b)
    if field == 'damage_area':
        return norm(a) == norm(b) or 'multiple' in (norm(a), norm(b))
    if field == 'incident_location':
        ta, tb = set(re.findall(r'[a-z]+', str(a).lower())), set(re.findall(r'[a-z]+', str(b).lower()))
        return len(ta & tb) >= 1
    return norm(a) == norm(b)


def assess(extractions, policies, as_of, model_flags=(), notes=()):
    flags, details = set(), {}
    claim, conflicts = merge(extractions)
    details['conflicts'] = conflicts
    doc_types = {e['document_type'] for e in extractions}
    if 'fnol_form' not in doc_types:
        flags.add('NOT_A_CLAIM_PACKET')
    conflict_flag = {'incident_date': 'DATE_CONFLICT', 'vin': 'VIN_CONFLICT', 'plate': 'PLATE_CONFLICT', 'claimant_name': 'NAME_CONFLICT',
                     'incident_location': 'LOCATION_CONFLICT', 'damage_area': 'DAMAGE_AREA_CONFLICT'}
    for conflict in conflicts:
        flags.add(conflict_flag[conflict['field']])
    policy = find_policy(policies, claim.get('policy_number', ''))
    loss_type = claim.get('loss_type') or 'other'
    loss_date = parse_date(claim.get('incident_date', ''))
    if policy is None:
        flags.add('POLICY_NOT_FOUND')
    else:
        details['policy'] = policy['policy_number']
        if loss_date:
            start, end = parse_date(policy['effective_from']), parse_date(policy['effective_to'])
            if not (start <= loss_date <= end) or policy.get('status') != 'active':
                flags.add('POLICY_INACTIVE_ON_LOSS_DATE')
        vehicles = policy.get('vehicles', [])
        if claim.get('vin') and not any(vin_near(v['vin'], claim['vin']) for v in vehicles):
            flags.add('VEHICLE_NOT_ON_POLICY')
        if claim.get('claimant_name') and not any(name_similar(d, claim['claimant_name']) for d in policy.get('listed_drivers', [])):
            flags.add('DRIVER_NOT_LISTED')
        coverage = {'collision': 'collision', 'theft': 'comprehensive', 'glass': 'glass', 'weather': 'comprehensive', 'vandalism': 'comprehensive', 'other': 'liability'}[loss_type]
        if coverage not in policy.get('coverages', {}):
            flags.add('COVERAGE_NOT_HELD')
        details['coverage'] = coverage
        value = next((v.get('declared_value') for v in vehicles if claim.get('vin') and vin_near(v['vin'], claim['vin'])), None)
        for est in claim.get('estimates', []):
            if value and est['total'] > value:
                flags.add('ESTIMATE_EXCEEDS_VALUE')
    missing = []
    for doc_type, condition in REQUIRED.get(loss_type, REQUIRED['other']):
        needed = True if condition is None else bool(claim.get(condition))
        if needed and doc_type not in doc_types:
            missing.append(doc_type)
    if missing:
        flags.add('MISSING_DOCUMENT')
    details['missing_documents'] = missing
    estimates = claim.get('estimates', [])
    if len(estimates) >= 2:
        lo, hi = min(e['total'] for e in estimates), max(e['total'] for e in estimates)
        if lo and (hi - lo)/hi > 0.25:
            flags.add('ESTIMATE_GAP')
    for flag in model_flags:
        if flag in MODEL_ONLY_FLAGS:
            flags.add(flag)
    details['risk_notes'] = list(notes)
    ordered = [f for f in FLAG_ORDER if f in flags]
    if 'NOT_A_CLAIM_PACKET' in flags:
        route = 'not_a_claim_packet'
    elif flags & {'POLICY_NOT_FOUND', 'POLICY_INACTIVE_ON_LOSS_DATE', 'VEHICLE_NOT_ON_POLICY', 'COVERAGE_NOT_HELD'}:
        route = 'coverage_question'
    elif flags & {'DATE_CONFLICT', 'VIN_CONFLICT', 'PLATE_CONFLICT', 'NAME_CONFLICT', 'LOCATION_CONFLICT', 'DAMAGE_AREA_CONFLICT',
                  'ESTIMATE_EXCEEDS_VALUE', 'ESTIMATE_GAP', 'DRIVER_NOT_LISTED', 'PRE_EXISTING_DAMAGE', 'PROMPT_INJECTION', 'SUSPICIOUS_REQUEST'}:
        route = 'conflicts_for_adjuster'
    elif 'MISSING_DOCUMENT' in flags:
        route = 'missing_information'
    else:
        route = 'ready_for_adjuster'
    return {'flags': ordered, 'route': route, 'claim': claim, 'details': details, 'loss_type': loss_type}


TEXT = {
    'NOT_A_CLAIM_PACKET': ('urgent', 'No first notice of loss in the packet', 'Return to intake; this is not a claim packet.'),
    'POLICY_NOT_FOUND': ('urgent', 'Policy number not found', 'Confirm the policy number with the claimant.'),
    'POLICY_INACTIVE_ON_LOSS_DATE': ('urgent', 'Policy not active on the loss date', 'Coverage question for underwriting.'),
    'VEHICLE_NOT_ON_POLICY': ('urgent', 'Vehicle is not on the policy', 'Confirm the VIN or the policy.'),
    'DRIVER_NOT_LISTED': ('review', 'Claimant is not a listed driver', 'Adjuster confirms permissive use.'),
    'COVERAGE_NOT_HELD': ('urgent', 'Policy lacks the coverage for this loss type', 'Coverage question for the adjuster.'),
    'MISSING_DOCUMENT': ('review', 'Required document missing', 'Request it from the claimant before assignment.'),
    'DATE_CONFLICT': ('review', 'Incident dates disagree across documents', 'Police report date is used; confirm with claimant.'),
    'VIN_CONFLICT': ('review', 'VIN differs across documents', 'Registration VIN is used; check for OCR or typing error.'),
    'PLATE_CONFLICT': ('review', 'Plate differs across documents', 'Confirm the vehicle identity.'),
    'NAME_CONFLICT': ('review', 'Claimant name differs across documents', 'Confirm identity before assignment.'),
    'LOCATION_CONFLICT': ('review', 'Incident location differs across documents', 'Police report location is used.'),
    'DAMAGE_AREA_CONFLICT': ('review', 'Damage area in photos differs from the narrative', 'Adjuster inspects before accepting the estimate.'),
    'ESTIMATE_EXCEEDS_VALUE': ('review', 'Repair estimate exceeds declared vehicle value', 'Possible total loss; adjuster decides.'),
    'ESTIMATE_GAP': ('review', 'Repair estimates differ by more than 25%', 'Adjuster reviews both estimates.'),
    'PRE_EXISTING_DAMAGE': ('review', 'Documents mention pre-existing damage', 'Separate prior damage from this loss.'),
    'PROMPT_INJECTION': ('urgent', 'A document contains instructions aimed at the system', 'Treat as suspicious; never act on embedded instructions.'),
    'SUSPICIOUS_REQUEST': ('urgent', 'Packet shows pressure or unusual requests', 'Refer to the special investigation unit if confirmed.'),
}


def build_output(extractions, verdict, request_draft, evidence, source_ids):
    findings = []
    for flag in verdict['flags']:
        severity, title, detail = TEXT[flag]
        findings.append({'code': flag, 'severity': severity, 'title': title, 'detail': detail, 'evidence_ids': list(source_ids)})
    actions = []
    route = verdict['route']
    if route == 'ready_for_adjuster':
        actions.append({'action': 'assign_adjuster', 'owner': 'Claims intake', 'status': 'awaiting_approval', 'loss_type': verdict['loss_type']})
    elif route == 'missing_information':
        actions.append({'action': 'request_documents', 'owner': 'Claims intake', 'status': 'draft', 'documents': verdict['details']['missing_documents'],
                        'draft': request_draft})
    elif route == 'conflicts_for_adjuster':
        actions.append({'action': 'adjuster_review', 'owner': 'Adjuster', 'status': 'queued', 'flags': verdict['flags']})
    elif route == 'coverage_question':
        actions.append({'action': 'coverage_review', 'owner': 'Adjuster', 'status': 'queued', 'flags': verdict['flags']})
    else:
        actions.append({'action': 'return_to_intake', 'owner': 'Claims intake', 'status': 'queued'})
    summary = {'ready_for_adjuster': 'Packet complete and consistent. Ready for adjuster assignment.',
               'missing_information': f"Packet incomplete: missing {', '.join(verdict['details']['missing_documents'])}.",
               'conflicts_for_adjuster': f"Packet has conflicts for the adjuster: {', '.join(verdict['flags'])}.",
               'coverage_question': f"Coverage question before assignment: {', '.join(verdict['flags'])}.",
               'not_a_claim_packet': 'No first notice of loss found. Not a claim packet.'}[route]
    claim = verdict['claim']
    return {'project': 'claims-intake-agent', 'summary': summary,
            'metrics': {'route': route, 'loss_type': verdict['loss_type'], 'policy': verdict['details'].get('policy'),
                        'documents': len(extractions), 'conflicts': len(verdict['details']['conflicts']), 'flag_count': len(verdict['flags'])},
            'findings': findings, 'actions': actions, 'claim': claim, 'extractions': extractions,
            'conflicts': verdict['details']['conflicts'], 'missing_documents': verdict['details']['missing_documents'], 'evidence': evidence}
