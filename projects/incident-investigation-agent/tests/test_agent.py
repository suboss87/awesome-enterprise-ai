"""Incident Investigation Agent: rules, boundaries, tools, baseline behaviour, example replay."""
import copy
import importlib.util
import sys
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from enterprise_ai.catalog import load_agent, load_baseline, load_scorer  # noqa: E402
from enterprise_ai.common import InputError  # noqa: E402
from enterprise_ai.evals import load_cases  # noqa: E402
from enterprise_ai.runner import example_input, example_replay, execute  # noqa: E402

SLUG = 'incident-investigation-agent'
PROJECT = ROOT/'projects'/SLUG
_spec = importlib.util.spec_from_file_location('incident_triage_t', PROJECT/'triage.py')
triage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(triage)
CASES = load_cases(SLUG)


def case(category, index=0):
    return [c for c in CASES if c['category'] == category][index]


def completion(*calls):
    return {'content': [{'type': 'tool_use', 'id': f'c{i}', 'name': name, 'input': payload} for i, (name, payload) in enumerate(calls)],
            'stop_reason': 'tool_use', 'model': 'test', 'response_id': 'x',
            'usage': {'input_tokens': 10, 'output_tokens': 5, 'cache_read_input_tokens': 0}}


def finish_call(result):
    return completion(('finish', result))


def item(c, item_id):
    return triage.index(c['input']['telemetry'])[item_id]


def perfect_result(c, **overrides):
    """Build a finish payload from the case's own frozen expectations (a 'perfect investigator')."""
    exp = c['expected']
    symptom = item(c, exp['symptom_alert_id'])
    ids = list(exp['cause_ids']) + [exp['symptom_alert_id']]
    if exp['reason_code'] == 'unknown':
        hypotheses, gaps = [], [f"logs for {exp['component']} between the window start and the first alert"]
    else:
        hypotheses = [{'claim': f"{exp['reason_code']} in {exp['component']} caused the errors.", 'component': exp['component'],
                       'evidence_ids': ids, 'disproving_check': 'Revert the change or restore the component and check whether the alert clears.',
                       'status': 'supported', 'confidence': 0.8}]
        gaps = []
    result = {'timeline': ids, 'hypotheses': hypotheses,
              'root_cause': {'component': exp['component'], 'reason_code': exp['reason_code'], 'first_ts': exp['first_ts'] or '', 'evidence_ids': ids},
              'rca_draft': 'Draft RCA.', 'data_gaps': gaps, 'injection_ids': list(exp.get('injection_ids', [])),
              'evidence': [{'source_id': exp['symptom_alert_id'], 'quote': symptom['text']}]}
    result.update(overrides)
    return result


class RulesTests(unittest.TestCase):
    def test_every_expected_route_is_reproduced_by_rules_from_a_perfect_result(self):
        """If the model investigates perfectly, triage.py alone must produce the labeled route and a perfect score."""
        scorer = load_scorer(SLUG)
        misses = []
        for c in CASES:
            out = execute(SLUG, c['input'], 'replay', replay=[finish_call(perfect_result(c))])
            s = scorer.score(c, out)
            if out['metrics']['route'] != c['expected']['route'] or not s['root_cause_correct'] or s['false_blame'] or s['fabricated_evidence']:
                misses.append((c['id'], out['metrics']['route'], out['findings'][0]['code'], s))
        self.assertEqual(misses, [])

    def test_cause_after_symptom_downgrades_to_unconfirmed(self):
        c = case('bad_deploy_latest')
        late_ts = triage.fmt_ts(item(c, c['expected']['symptom_alert_id'])['ts'] + timedelta(minutes=3))
        result = perfect_result(c)
        result['root_cause']['first_ts'] = late_ts
        out = execute(SLUG, c['input'], 'replay', replay=[finish_call(result)])
        self.assertEqual(out['metrics']['route'], 'unconfirmed')
        self.assertIn('CAUSE_AFTER_SYMPTOM', [f['code'] for f in out['findings']])
        self.assertFalse(out['metrics']['cause_before_symptom'])

    def test_evidence_outside_the_window_is_dropped(self):
        c = case('bad_deploy_latest')
        window = triage.window_of(c['input']['incident'])
        old = next(d for d in c['input']['telemetry']['deploys'] if triage.parse_ts(d['ts']) < window[0])
        result = perfect_result(c)
        result['root_cause']['evidence_ids'] = [old['id'], c['expected']['symptom_alert_id']]
        out = execute(SLUG, c['input'], 'replay', replay=[finish_call(result)])
        codes = [f['code'] for f in out['findings']]
        self.assertIn('EVIDENCE_OUTSIDE_WINDOW', codes)
        self.assertIn('MISSING_CAUSE_EVIDENCE', codes)
        self.assertEqual(out['metrics']['route'], 'unconfirmed')
        self.assertNotIn(old['id'], out['root_cause']['evidence_ids'])

    def test_unknown_reason_routes_to_insufficient_evidence_with_named_gap(self):
        c = case('insufficient_evidence')
        out = execute(SLUG, c['input'], 'replay', replay=[finish_call(perfect_result(c))])
        self.assertEqual(out['metrics']['route'], 'insufficient_evidence')
        self.assertTrue(load_scorer(SLUG).score(c, out)['data_gap_named'])
        self.assertEqual(out['actions'][0]['action'], 'collect_missing_data')


class BoundaryTests(unittest.TestCase):
    def test_model_cannot_force_confirmed_without_cause_evidence(self):
        """Confidence 0.99 and only symptom alerts cited: the rules refuse `confirmed`."""
        c = case('bad_deploy_latest')
        result = perfect_result(c)
        alerts = [a['id'] for a in c['input']['telemetry']['alerts'][:3]]
        result['root_cause']['evidence_ids'] = alerts
        result['hypotheses'][0]['evidence_ids'] = alerts
        result['hypotheses'][0]['confidence'] = 0.99
        out = execute(SLUG, c['input'], 'replay', replay=[finish_call(result)])
        self.assertEqual(out['metrics']['route'], 'unconfirmed')
        self.assertIn('MISSING_CAUSE_EVIDENCE', [f['code'] for f in out['findings']])
        self.assertEqual(out['model_recommendation']['confidence'], 0.99)

    def test_missing_disproving_check_blocks_confirmed(self):
        c = case('config_flag_change')
        result = perfect_result(c)
        result['hypotheses'][0]['disproving_check'] = ''
        out = execute(SLUG, c['input'], 'replay', replay=[finish_call(result)])
        self.assertEqual(out['metrics']['route'], 'unconfirmed')
        self.assertIn('NO_DISPROVING_CHECK', [f['code'] for f in out['findings']])
        self.assertEqual(load_scorer(SLUG).score(c, out)['hypotheses_with_disproving_check'], 0.0)

    def test_fabricated_evidence_id_is_dropped_and_counted(self):
        c = case('bad_deploy_latest')
        result = perfect_result(c)
        result['root_cause']['evidence_ids'].append('dep-999')
        result['timeline'].append('log-999')
        out = execute(SLUG, c['input'], 'replay', replay=[finish_call(result)])
        self.assertIn('EVIDENCE_NOT_FOUND', [f['code'] for f in out['findings']])
        self.assertEqual(load_scorer(SLUG).score(c, out)['fabricated_evidence'], 2)
        self.assertNotIn('dep-999', out['root_cause']['evidence_ids'])

    def test_fabricated_quote_is_rejected_then_corrected(self):
        c = case('bad_deploy_latest')
        bad = perfect_result(c)
        bad['evidence'] = [{'source_id': c['expected']['symptom_alert_id'], 'quote': 'this sentence is not in the alert'}]
        out = execute(SLUG, c['input'], 'replay', replay=[finish_call(bad), finish_call(perfect_result(c))])
        self.assertTrue(any(e['event'] == 'finish_rejected' for e in out['execution']['events']))
        self.assertEqual(load_scorer(SLUG).score(c, out)['fabricated_evidence'], 1)

    def test_write_tools_are_recorded_not_executed(self):
        c = case('bad_deploy_latest')
        writes = completion(('propose_mitigation', {'action': 'rollback', 'service': c['expected']['component'], 'runbook_id': '', 'reason': 'bad deploy'}),
                            ('post_rca_draft', {'text_body': 'RCA text'}))
        out = execute(SLUG, c['input'], 'replay', replay=[writes, finish_call(perfect_result(c))])
        self.assertEqual([p['status'] for p in out['proposed_actions']], ['awaiting_approval', 'awaiting_approval'])
        statuses = {a['action']: a['status'] for a in out['actions']}
        self.assertEqual(statuses['propose_mitigation'], 'awaiting_approval')
        self.assertEqual(statuses['post_rca_draft'], 'awaiting_approval')
        self.assertTrue(out['human_review_required'])

    def test_injection_ids_become_an_urgent_finding(self):
        c = case('prompt_injection_in_log_line')
        out = execute(SLUG, c['input'], 'replay', replay=[finish_call(perfect_result(c))])
        finding = next(f for f in out['findings'] if f['code'] == 'PROMPT_INJECTION')
        self.assertEqual(finding['severity'], 'urgent')
        self.assertEqual(finding['evidence_ids'], c['expected']['injection_ids'])
        self.assertTrue(load_scorer(SLUG).score(c, out)['injection_flagged'])

    def test_pagination_caps_every_read_at_fifty_items(self):
        c = case('alert_storm_single_cause')
        tools = _tools(c)
        first = tools['get_alerts']('', '', '', 1)
        self.assertEqual(len(first['items']), triage.PAGE_SIZE)
        self.assertTrue(first['has_more'])
        self.assertGreaterEqual(first['total'], 150)
        seen, page = [], 1
        while True:
            chunk = tools['get_alerts']('', '', '', page)
            seen += [i['id'] for i in chunk['items']]
            if not chunk['has_more']:
                break
            page += 1
        self.assertEqual(len(seen), first['total'])
        self.assertEqual(len(set(seen)), len(seen))
        logs = tools['query_logs']('', '', '', '', '', 1)
        self.assertLessEqual(len(logs['items']), triage.PAGE_SIZE)
        with self.assertRaises(InputError):
            tools['get_alerts']('', '', '', 0)

    def test_tools_filter_by_service_pattern_level_and_window(self):
        c = case('dependency_outage_no_deploy')
        tools = _tools(c)
        component = c['expected']['component']
        fatal = tools['query_logs'](component, '', 'FATAL', '', '', 1)
        self.assertTrue(fatal['items'])
        self.assertTrue(all(i['level'] == 'FATAL' and i['service'] == component for i in fatal['items']))
        errors = tools['query_logs'](component, '', 'ERROR', '', '', 1)
        self.assertGreaterEqual(errors['total'], fatal['total'])
        none = tools['query_logs'](component, 'no such pattern anywhere', '', '', '', 1)
        self.assertEqual(none['total'], 0)
        window = c['input']['incident']['window']
        deploys = tools['get_deploys']('', '', '', )
        self.assertTrue(all(window['from'] <= d['ts'] <= window['to'] for d in deploys['items']))
        early = tools['get_deploys']('', '2026-01-01T00:00:00Z', window['from'])
        self.assertTrue(all(d.get('outside_incident_window') for d in early['items']))
        with self.assertRaises(InputError):
            tools['query_logs']('', '', 'VERBOSE', '', '', 1)
        deps = tools['get_dependencies'](c['input']['incident']['services_impacted'][0])
        self.assertIn(component, deps['depends_on'])

    def test_input_contract_rejects_unknown_fields_bad_timestamps_and_duplicate_ids(self):
        agent = load_agent(SLUG)
        data = copy.deepcopy(case('bad_deploy_latest')['input'])
        data['surprise'] = 1
        with self.assertRaises(InputError):
            agent.validate(data)
        data = copy.deepcopy(case('bad_deploy_latest')['input'])
        data['telemetry']['alerts'][0]['ts'] = 'yesterday'
        with self.assertRaises(InputError):
            agent.validate(data)
        data = copy.deepcopy(case('bad_deploy_latest')['input'])
        data['telemetry']['logs'][1]['id'] = data['telemetry']['logs'][0]['id']
        with self.assertRaises(InputError):
            agent.validate(data)
        data = copy.deepcopy(case('bad_deploy_latest')['input'])
        data['incident']['window']['to'] = data['incident']['window']['from']
        with self.assertRaises(InputError):
            agent.validate(data)


class BaselineAndExampleTests(unittest.TestCase):
    def test_baseline_wins_latest_deploy_and_is_fooled_by_delayed_effect_and_capacity(self):
        scorer = load_scorer(SLUG)
        base = load_baseline(SLUG)
        for c in CASES:
            s = scorer.score(c, base.run(c['input']))
            if c['category'] == 'bad_deploy_latest':
                self.assertTrue(s['root_cause_correct'] and s['first_ts_within_2min'], c['id'])
            if c['category'] == 'bad_deploy_older_delayed_effect':
                self.assertTrue(s['false_blame'], c['id'])
                self.assertFalse(s['first_ts_within_2min'], c['id'])
            if c['category'] == 'capacity_exhaustion':
                self.assertFalse(s['root_cause_correct'], c['id'])
            if c['category'] == 'dependency_outage_innocent_deploy':
                self.assertTrue(s['false_blame'], c['id'])
            self.assertEqual(s['fabricated_evidence'], 0, c['id'])

    @unittest.skipUnless((PROJECT/'examples/replay.json').is_file(), 'examples/replay.json not recorded yet')
    def test_example_replay_runs_offline(self):
        out = execute(SLUG, example_input(SLUG), 'replay', replay=example_replay(SLUG))
        self.assertEqual(out['execution']['mode'], 'replay')
        self.assertIn(out['metrics']['route'], triage.ROUTES)
        self.assertTrue(out['hypotheses'])
        self.assertTrue(out['root_cause']['evidence_ids'])


def _tools(c):
    agent = load_agent(SLUG)
    incident, telemetry = agent.validate(c['input'])
    return {t.name: t.fn for t in agent.build_tools(incident, telemetry)}


if __name__ == '__main__':
    unittest.main()
