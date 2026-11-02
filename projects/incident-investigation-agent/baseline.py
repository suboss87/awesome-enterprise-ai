"""Rules-only baseline: "the latest change before the first alert did it".

What an on-call team ships without a model: take the impacted services, find the
most recent deploy or config change before the first alert and name it; with no
change, blame the first dependency that shows an alert or an error; otherwise say
unknown. One templated hypothesis with a templated rollback check. The verdict
goes through the same `triage.py` rules as the agent, so the comparison isolates
the reading and reasoning step.
"""
import importlib.util
from pathlib import Path

_here = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('incident_triage_b', _here/'triage.py')
triage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(triage)
_aspec = importlib.util.spec_from_file_location('incident_agent_b', _here/'agent.py')
agent_module = importlib.util.module_from_spec(_aspec)
_aspec.loader.exec_module(agent_module)


def _latest_change(entries, services, window, before):
    changes = [e for e in entries.values() if e['kind'] in ('deploy', 'config_change') and e['service'] in services
               and triage.in_window(e, window) and e['ts'] <= before]
    return max(changes, key=lambda e: e['ts']) if changes else None


def _failing_dependency(entries, telemetry, services, window, before):
    """First dependency (direct, then transitive) with an alert or ERROR/FATAL log before the first alert."""
    candidates = []
    for service in services:
        for dep in triage.dependencies_of(telemetry, service):
            failures = [e for e in entries.values()
                        if (e['kind'] == 'alert' or (e['kind'] == 'log' and e['raw']['level'] in ('ERROR', 'FATAL')))
                        and e['service'] == dep and triage.in_window(e, window) and e['ts'] <= before]
            if failures:
                first = min(failures, key=lambda e: e['ts'])
                candidates.append((first['ts'], dep, sorted(failures, key=lambda e: e['ts'])))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    return candidates[0]


def investigate(incident, telemetry):
    entries = triage.index(telemetry)
    window = triage.window_of(incident)
    impacted = incident['services_impacted']
    symptom = triage.first_symptom(entries, incident, window)
    before = symptom['ts'] if symptom else window[1]
    symptom_ids = [symptom['raw']['id']] if symptom else []
    alerts = sorted((e for e in entries.values() if e['kind'] == 'alert' and triage.in_window(e, window)), key=lambda e: e['ts'])
    timeline = [e['raw']['id'] for e in alerts][:triage.MAX_TIMELINE]
    change = _latest_change(entries, impacted, window, before)
    if change is not None:
        reason = 'bad_deploy' if change['kind'] == 'deploy' else 'config_change'
        what = f"deploy {change['raw']['sha']}" if change['kind'] == 'deploy' else f"config change {change['raw']['key']}"
        return {'timeline': [change['raw']['id']] + timeline,
                'hypotheses': [{'claim': f"The most recent change on {change['service']} before the first alert ({what}) caused the errors.",
                                'component': change['service'], 'evidence_ids': [change['raw']['id']] + symptom_ids,
                                'disproving_check': f"Roll back {what} on {change['service']} and check whether the alert clears within 10 minutes.",
                                'status': 'supported', 'confidence': 0.6}],
                'root_cause': {'component': change['service'], 'reason_code': reason, 'first_ts': change['raw']['ts'],
                               'evidence_ids': [change['raw']['id']] + symptom_ids},
                'rca_draft': f"{incident['id']}: {what} on {change['service']} at {change['raw']['ts']} preceded the first alert; rollback proposed.",
                'data_gaps': [], 'injection_ids': [],
                'evidence': [{'source_id': change['raw']['id'], 'quote': change['text']}] + [{'source_id': symptom['raw']['id'], 'quote': symptom['text']} for _ in symptom_ids]}
    failing = _failing_dependency(entries, telemetry, impacted, window, before)
    if failing is not None:
        first_ts, dep, failures = failing
        return {'timeline': [f['raw']['id'] for f in failures[:5]] + timeline,
                'hypotheses': [{'claim': f'Dependency {dep} failed and the impacted services inherited its errors.', 'component': dep,
                                'evidence_ids': [f['raw']['id'] for f in failures[:5]] + symptom_ids,
                                'disproving_check': f'Check whether {dep} recovered before the impacted services did; if not, the dependency is not the cause.',
                                'status': 'supported', 'confidence': 0.5}],
                'root_cause': {'component': dep, 'reason_code': 'dependency_outage', 'first_ts': triage.fmt_ts(first_ts),
                               'evidence_ids': [f['raw']['id'] for f in failures[:5]] + symptom_ids},
                'rca_draft': f"{incident['id']}: no change on the impacted services; dependency {dep} showed failures from {triage.fmt_ts(first_ts)}.",
                'data_gaps': [], 'injection_ids': [],
                'evidence': [{'source_id': failures[0]['raw']['id'], 'quote': failures[0]['text']}] + [{'source_id': symptom['raw']['id'], 'quote': symptom['text']} for _ in symptom_ids]}
    return {'timeline': timeline, 'hypotheses': [],
            'root_cause': {'component': impacted[0], 'reason_code': 'unknown', 'first_ts': '', 'evidence_ids': symptom_ids},
            'rca_draft': f"{incident['id']}: no deploy, config change or dependency failure found before the first alert.",
            'data_gaps': [f"No deploy, config change or dependency failure found for {', '.join(impacted)} before the first alert."],
            'injection_ids': [], 'evidence': [{'source_id': symptom['raw']['id'], 'quote': symptom['text']} for _ in symptom_ids]}


def run(data):
    incident, telemetry = agent_module.validate(data)
    result = investigate(incident, telemetry)
    verdict = triage.evaluate(result, telemetry, incident)
    mitigation = []
    if verdict['route'] != 'insufficient_evidence':
        mitigation.append({'action': 'rollback' if verdict['reason_code'] in ('bad_deploy', 'config_change') else 'enable circuit breaker',
                           'service': verdict['component'], 'runbook_id': '', 'reason': result['hypotheses'][0]['claim']})
    output = triage.build_output(verdict, result['rca_draft'], mitigation, [], result['evidence'], incident)
    output['baseline'] = 'latest-change-before-alert'
    return output
