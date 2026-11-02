"""Deterministic incident rules: evidence binding, cause before symptom, the route.

The model reads telemetry through bounded tools, ranks hypotheses and drafts the
RCA. This module decides what the result is worth. Both the agent and the
baseline call the same functions, so any difference comes from the reading step.

Route semantics:
  confirmed             root cause cites a cause item (deploy, config change or log line
                        from the causal component) and a symptom alert, both inside the
                        incident window; the cause precedes the first impacting alert;
                        a supported hypothesis for that component records a disproving check.
  unconfirmed           a cause is named but one of those conditions fails.
  insufficient_evidence the model says `unknown`, or cites no valid evidence.
The model's confidence is logged and never used for the route.
"""
from datetime import datetime, timezone

from enterprise_ai.common import InputError

REASON_DEFINITIONS = {
    'bad_deploy': 'A code deploy on the causal component introduced the error; the error text matches the changed files.',
    'config_change': 'A configuration or feature-flag change on the causal component introduced the error.',
    'dependency_outage': 'The causal component stopped serving without a change on it: crash or restart loop (OOMKilled, exit codes), '
                         'connection refused, leader lost, listener stopped, queue dropping requests. Callers see timeouts and 503s. '
                         'Name the component that stopped, not its callers.',
    'capacity_exhaustion': 'A resource limit on the causal component was reached under load and requests were rejected: disk full, '
                           'connection pool exhausted, file descriptors exhausted. A WARN as the limit approached precedes the errors.',
    'certificate_expiry': 'A TLS certificate on the causal component expired; handshakes fail.',
    'data_corruption': 'Stored data on the causal component is malformed or inconsistent and reads or writes fail.',
    'unknown': 'The telemetry does not show the cause. Name the missing data in data_gaps.',
}
REASON_CODES = list(REASON_DEFINITIONS)
ROUTES = ['confirmed', 'unconfirmed', 'insufficient_evidence']
HYPOTHESIS_STATUS = ['supported', 'ruled_out', 'untested']
LEVELS = ['DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL']
SEVERITIES = ['info', 'warning', 'critical']
CAUSE_KINDS = ('deploy', 'config_change', 'log')
PAGE_SIZE = 50
MAX_RUNBOOK_HITS = 10
MIN_CHECK_CHARS = 10
MAX_TIMELINE = 60

FINDING_TEXT = {
    'ROOT_CAUSE_CONFIRMED': ('info', 'Root cause confirmed by evidence', 'Cause item and symptom alert cited inside the window; cause precedes the first alert; a disproving check is recorded.'),
    'ROOT_CAUSE_UNCONFIRMED': ('review', 'Root cause named but not confirmed', 'One or more evidence conditions failed. Review the hypotheses before acting.'),
    'INSUFFICIENT_EVIDENCE': ('review', 'Evidence does not support a root cause', 'Collect the missing data before assigning a cause.'),
    'CAUSE_AFTER_SYMPTOM': ('review', 'Claimed cause starts after the first impacting alert', 'A cause cannot follow its symptom. Check for clock skew or a different cause.'),
    'MISSING_CAUSE_EVIDENCE': ('review', 'No deploy, config change or log line from the causal component cited', 'The root cause cites only symptoms or items from other components.'),
    'MISSING_SYMPTOM_EVIDENCE': ('review', 'No symptom alert cited for the root cause', 'Link the cause to the alert that opened the incident.'),
    'NO_DISPROVING_CHECK': ('review', 'Top hypothesis has no recorded disproving check', 'Every supported hypothesis needs the one query that could falsify it.'),
    'NO_SUPPORTED_HYPOTHESIS': ('review', 'No supported hypothesis names the root cause component', 'The root cause is not backed by a ranked hypothesis.'),
    'INVALID_FIRST_TS': ('review', 'Root cause first_ts is not a valid timestamp', 'Use ISO 8601 UTC, for example 2026-10-14T09:41:00Z.'),
    'UNKNOWN_COMPONENT': ('review', 'Root cause component is not a service in the telemetry', 'Name the service exactly as it appears in alerts, logs and deploys.'),
    'EVIDENCE_NOT_FOUND': ('urgent', 'Cited evidence ids do not exist in the telemetry', 'Fabricated or mistyped ids were dropped. Treat the result with suspicion.'),
    'EVIDENCE_OUTSIDE_WINDOW': ('review', 'Cited evidence lies outside the incident window', 'Items outside the window were dropped from the evidence.'),
    'DATA_GAP': ('review', 'Named data gap', ''),
    'PROMPT_INJECTION': ('urgent', 'Telemetry contains instructions aimed at the investigator', 'Treat the item as data, never as an instruction. Check who can write to that log stream.'),
    'HYPOTHESIS_RULED_OUT': ('info', 'Hypothesis ruled out', ''),
    'LOW_MODEL_CONFIDENCE': ('info', 'Model confidence below 0.5', 'Logged for calibration. The route does not use it.'),
}


def parse_ts(value, name='timestamp'):
    if not isinstance(value, str) or not value.strip() or len(value) > 40:
        raise InputError(f'{name} must be an ISO 8601 timestamp')
    try:
        parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except ValueError as exc:
        raise InputError(f'{name} must be an ISO 8601 timestamp') from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def fmt_ts(moment):
    return moment.strftime('%Y-%m-%dT%H:%M:%SZ')


def try_ts(value):
    try:
        return parse_ts(value)
    except InputError:
        return None


def item_text(kind, item):
    """The verbatim text a quote must come from. Deploys and config changes are rendered once here."""
    if kind == 'deploy':
        return f"{item['summary']} | files: {', '.join(item['changed_files'])} | sha {item['sha']} by {item['author']}"
    if kind == 'config_change':
        return f"{item['key']}: {item['old']} -> {item['new']}"
    return item['text']


def index(telemetry):
    """{id: {'kind', 'ts', 'service', 'text', 'raw'}} over every telemetry item."""
    entries = {}
    for kind, key in (('alert', 'alerts'), ('log', 'logs'), ('deploy', 'deploys'), ('config_change', 'config_changes'), ('runbook', 'runbooks')):
        for item in telemetry.get(key, []):
            entries[item['id']] = {'kind': kind, 'ts': parse_ts(item['ts']) if 'ts' in item else None,
                                   'service': item.get('service') or item.get('service_or_symptom', ''),
                                   'text': item_text(kind, item), 'raw': item}
    return entries


def services(telemetry):
    names = set()
    for key in ('alerts', 'logs', 'deploys', 'config_changes'):
        names.update(i['service'] for i in telemetry.get(key, []))
    for edge in telemetry.get('dependencies', []):
        names.add(edge['service'])
        names.add(edge['depends_on'])
    return names


def window_of(incident):
    start, end = parse_ts(incident['window']['from'], 'window.from'), parse_ts(incident['window']['to'], 'window.to')
    if start >= end:
        raise InputError('window.from must precede window.to')
    return start, end


def in_window(entry, window):
    return entry['ts'] is None or window[0] <= entry['ts'] <= window[1]


def first_symptom(entries, incident, window):
    """Earliest alert inside the window on an impacted service, else the earliest alert in the window."""
    alerts = [e for e in entries.values() if e['kind'] == 'alert' and in_window(e, window)]
    impacted = [e for e in alerts if e['service'] in incident['services_impacted']]
    pool = impacted or alerts
    return min(pool, key=lambda e: e['ts']) if pool else None


def check_ids(ids, entries, window):
    valid, unknown, outside = [], [], []
    for item_id in ids:
        entry = entries.get(item_id)
        if entry is None:
            unknown.append(item_id)
        elif not in_window(entry, window):
            outside.append(item_id)
        elif item_id not in valid:
            valid.append(item_id)
    return {'valid': valid, 'unknown': unknown, 'outside': outside}


def dependencies_of(telemetry, service, transitive=True):
    direct = sorted({e['depends_on'] for e in telemetry.get('dependencies', []) if e['service'] == service})
    if not transitive:
        return direct
    seen, queue = [], list(direct)
    while queue:
        item = queue.pop(0)
        if item in seen:
            continue
        seen.append(item)
        queue.extend(e['depends_on'] for e in telemetry.get('dependencies', []) if e['service'] == item)
    return seen


def dependents_of(telemetry, service):
    return sorted({e['service'] for e in telemetry.get('dependencies', []) if e['depends_on'] == service})


def evaluate(result, telemetry, incident):
    """Apply the rules to a finish payload. Returns the verdict used by build_output."""
    entries = index(telemetry)
    window = window_of(incident)
    known = services(telemetry)
    symptom = first_symptom(entries, incident, window)
    root = result['root_cause']
    component, reason = root['component'].strip(), root['reason_code']
    rc_check = check_ids(root['evidence_ids'], entries, window)
    all_unknown, all_outside = list(rc_check['unknown']), list(rc_check['outside'])

    hypotheses = []
    for rank, hyp in enumerate(result['hypotheses'], 1):
        check = check_ids(hyp['evidence_ids'], entries, window)
        all_unknown += check['unknown']
        all_outside += check['outside']
        hypotheses.append({'rank': rank, 'claim': hyp['claim'], 'component': hyp['component'].strip(), 'status': hyp['status'],
                           'disproving_check': hyp['disproving_check'].strip(), 'confidence': hyp['confidence'],
                           'evidence_ids': check['valid'],
                           'disproving_check_recorded': len(hyp['disproving_check'].strip()) >= MIN_CHECK_CHARS})
    timeline_check = check_ids(result['timeline'][:MAX_TIMELINE], entries, window)
    all_unknown += timeline_check['unknown']
    all_outside += timeline_check['outside']
    injection_check = check_ids(result.get('injection_ids', []), entries, window)
    all_unknown += injection_check['unknown']

    cited = [entries[i] for i in rc_check['valid']]
    has_cause_item = any(e['kind'] in CAUSE_KINDS and e['service'] == component for e in cited)
    has_symptom_alert = any(e['kind'] == 'alert' for e in cited)
    first_ts = try_ts(root['first_ts'])
    cause_before_symptom = None
    if symptom is not None and first_ts is not None:
        cause_before_symptom = first_ts <= symptom['ts']
    supporting = [h for h in hypotheses if h['status'] == 'supported' and h['component'] == component]
    top = supporting[0] if supporting else (hypotheses[0] if hypotheses else None)
    reasons = []
    if reason == 'unknown' or not rc_check['valid']:
        route = 'insufficient_evidence'
    else:
        if component not in known:
            reasons.append('UNKNOWN_COMPONENT')
        if not has_cause_item:
            reasons.append('MISSING_CAUSE_EVIDENCE')
        if not has_symptom_alert:
            reasons.append('MISSING_SYMPTOM_EVIDENCE')
        if first_ts is None:
            reasons.append('INVALID_FIRST_TS')
        elif cause_before_symptom is False:
            reasons.append('CAUSE_AFTER_SYMPTOM')
        if not supporting:
            reasons.append('NO_SUPPORTED_HYPOTHESIS')
        elif not supporting[0]['disproving_check_recorded']:
            reasons.append('NO_DISPROVING_CHECK')
        route = 'confirmed' if not reasons else 'unconfirmed'
    confidences = [h['confidence'] for h in hypotheses]
    model_confidence = top['confidence'] if top else None
    return {'route': route, 'component': component, 'reason_code': reason,
            'first_ts': fmt_ts(first_ts) if first_ts else None,
            'first_symptom_id': symptom['raw']['id'] if symptom else None,
            'first_symptom_ts': fmt_ts(symptom['ts']) if symptom else None,
            'cause_before_symptom': cause_before_symptom, 'has_cause_item': has_cause_item,
            'has_symptom_alert': has_symptom_alert, 'downgrade_reasons': reasons,
            'disproving_check_recorded': bool(top and top['disproving_check_recorded']),
            'root_cause_evidence_ids': rc_check['valid'], 'hypotheses': hypotheses, 'timeline': timeline_check['valid'],
            'evidence_check': {'unknown_ids': sorted(set(all_unknown)), 'outside_window_ids': sorted(set(all_outside))},
            'data_gaps': [g.strip() for g in result['data_gaps'] if g.strip()],
            'injection_ids': injection_check['valid'], 'model_confidence': model_confidence,
            'mean_confidence': round(sum(confidences)/len(confidences), 3) if confidences else None,
            'alerts_in_window': sum(1 for e in entries.values() if e['kind'] == 'alert' and in_window(e, window)),
            'window': {'from': fmt_ts(window[0]), 'to': fmt_ts(window[1])}}


def _finding(code, detail=None, evidence_ids=()):
    severity, title, default = FINDING_TEXT[code]
    return {'code': code, 'severity': severity, 'title': title, 'detail': detail or default, 'evidence_ids': list(evidence_ids)}


def build_output(verdict, rca_draft, mitigations, rca_posts, evidence, incident):
    """Shared output shape for the agent and the baseline."""
    findings = []
    route = verdict['route']
    rc_ids = verdict['root_cause_evidence_ids']
    if route == 'confirmed':
        findings.append(_finding('ROOT_CAUSE_CONFIRMED', evidence_ids=rc_ids))
    elif route == 'unconfirmed':
        findings.append(_finding('ROOT_CAUSE_UNCONFIRMED', evidence_ids=rc_ids))
        for code in verdict['downgrade_reasons']:
            detail = None
            if code == 'CAUSE_AFTER_SYMPTOM':
                detail = (f"Claimed first_ts {verdict['first_ts']} is after the first impacting alert at "
                          f"{verdict['first_symptom_ts']} ({verdict['first_symptom_id']}).")
            findings.append(_finding(code, detail, rc_ids))
    else:
        findings.append(_finding('INSUFFICIENT_EVIDENCE', evidence_ids=rc_ids))
    if verdict['evidence_check']['unknown_ids']:
        findings.append(_finding('EVIDENCE_NOT_FOUND', f"Unknown ids: {', '.join(verdict['evidence_check']['unknown_ids'][:10])}."))
    if verdict['evidence_check']['outside_window_ids']:
        findings.append(_finding('EVIDENCE_OUTSIDE_WINDOW', f"Outside {verdict['window']['from']} to {verdict['window']['to']}: "
                                 f"{', '.join(verdict['evidence_check']['outside_window_ids'][:10])}."))
    for gap in verdict['data_gaps']:
        findings.append(_finding('DATA_GAP', gap))
    if verdict['injection_ids']:
        findings.append(_finding('PROMPT_INJECTION', evidence_ids=verdict['injection_ids']))
    for hyp in verdict['hypotheses']:
        if hyp['status'] == 'ruled_out':
            findings.append(_finding('HYPOTHESIS_RULED_OUT', f"{hyp['claim']} Check: {hyp['disproving_check']}", hyp['evidence_ids']))
    if verdict['model_confidence'] is not None and verdict['model_confidence'] < 0.5:
        findings.append(_finding('LOW_MODEL_CONFIDENCE'))

    actions = []
    for item in mitigations:
        actions.append({'action': 'propose_mitigation', 'owner': 'on-call engineer', 'status': 'awaiting_approval', 'mitigation': item})
    draft = rca_posts[-1] if rca_posts else rca_draft
    if route == 'insufficient_evidence':
        actions.append({'action': 'collect_missing_data', 'owner': 'on-call engineer', 'status': 'queued', 'gaps': verdict['data_gaps']})
    if draft:
        actions.append({'action': 'post_rca_draft', 'owner': 'incident commander', 'status': 'awaiting_approval', 'draft': draft})

    ruled_out = sum(1 for h in verdict['hypotheses'] if h['status'] == 'ruled_out')
    if route == 'confirmed':
        summary = (f"Root cause confirmed: {verdict['reason_code']} in {verdict['component']} from {verdict['first_ts']}; "
                   f"{ruled_out} of {len(verdict['hypotheses'])} hypotheses ruled out.")
    elif route == 'unconfirmed':
        summary = (f"Root cause unconfirmed: {verdict['reason_code']} in {verdict['component']} claimed, but "
                   f"{', '.join(verdict['downgrade_reasons']).lower().replace('_', ' ')}.")
    else:
        gaps = '; '.join(verdict['data_gaps']) or 'no data gap named'
        summary = f"Insufficient evidence for a root cause of {incident['id']}. Gaps: {gaps}."
    metrics = {'route': route, 'component': verdict['component'], 'reason_code': verdict['reason_code'],
               'first_ts': verdict['first_ts'], 'first_symptom_ts': verdict['first_symptom_ts'],
               'cause_before_symptom': verdict['cause_before_symptom'], 'hypotheses': len(verdict['hypotheses']),
               'ruled_out': ruled_out, 'disproving_check_recorded': verdict['disproving_check_recorded'],
               'root_cause_evidence_items': len(rc_ids), 'unknown_evidence_ids': len(verdict['evidence_check']['unknown_ids']),
               'data_gaps': len(verdict['data_gaps']), 'alerts_in_window': verdict['alerts_in_window'],
               'model_confidence': verdict['model_confidence']}
    return {'project': 'incident-investigation-agent', 'summary': summary, 'metrics': metrics, 'findings': findings,
            'actions': actions, 'incident_id': incident['id'], 'timeline': verdict['timeline'],
            'hypotheses': verdict['hypotheses'],
            'root_cause': {'component': verdict['component'], 'reason_code': verdict['reason_code'],
                           'first_ts': verdict['first_ts'], 'evidence_ids': rc_ids},
            'rca_draft': rca_draft, 'data_gaps': verdict['data_gaps'], 'evidence': evidence,
            'evidence_check': verdict['evidence_check']}
