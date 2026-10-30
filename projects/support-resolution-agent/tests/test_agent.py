"""Support Resolution Agent: contract, rules, permission boundaries, baseline, example replay."""
import copy
import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from enterprise_ai.catalog import load_agent, load_baseline, load_scorer  # noqa: E402
from enterprise_ai.common import InputError  # noqa: E402
from enterprise_ai.evals import load_cases  # noqa: E402
from enterprise_ai.runner import example_input, example_replay, execute  # noqa: E402

SLUG = 'support-resolution-agent'
PROJECT = ROOT/'projects'/SLUG
_spec = importlib.util.spec_from_file_location('support_policy_t', PROJECT/'policy.py')
policy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(policy)
CASES = load_cases(SLUG)


def case(category, index=0, **where):
    matches = [c for c in CASES if c['category'] == category and all(c['expected'].get(k) == v for k, v in where.items())]
    return matches[index]


def completion(*blocks):
    return {'content': list(blocks), 'stop_reason': 'tool_use', 'model': 'test', 'response_id': 'x',
            'usage': {'input_tokens': 10, 'output_tokens': 5, 'cache_read_input_tokens': 0}}


def tool_use(name, **kwargs):
    return {'type': 'tool_use', 'id': f'call_{name}_{len(str(kwargs))}', 'name': name, 'input': kwargs}


def finish_call(result):
    return completion(tool_use('finish', **result))


def section_quote(c, section_id):
    for pol in c['input']['systems']['policies']:
        for section in pol['sections']:
            if section['section_id'] == section_id:
                return pol['policy_id'], policy.sentences(section['text'])[0]
    raise KeyError(section_id)


def perfect_result(c, intent=None, order_id=None, action=None, amount=None, skus=None, cite=None, flags=(), reply=None, needs_escalation=None):
    """A finish payload built from the case's own labels: what a perfect reader would submit."""
    exp = c['expected']
    intent = intent or exp['intent']
    order_id = exp['order_id'] if order_id is None else order_id
    action = action or exp['action']
    amount = exp['amount'] if amount is None else amount
    cited = []
    for sid in (cite if cite is not None else exp['must_cite']):
        pid, quote = section_quote(c, sid)
        cited.append({'policy_id': pid, 'section_id': sid, 'quote': quote})
    return {'intent': intent, 'order_id': order_id or '',
            'cited_policy': cited,
            'draft_reply': reply if reply is not None else 'Thank you for contacting us. We have reviewed your request and will update you once a colleague has approved the next step.',
            'proposed_action': {'type': action, 'order_id': order_id or '', 'amount': float(amount or 0), 'skus': list(skus if skus is not None else exp.get('skus', [])),
                                'reason': 'per policy'},
            'needs_escalation': exp['needs_escalation'] if needs_escalation is None else needs_escalation,
            'flags': list(flags),
            'evidence': [{'source_id': c['input']['ticket']['id'], 'quote': exp['order_id'] or c['input']['ticket']['text'][:20]}]}


def run_perfect(c, **overrides):
    return execute(SLUG, c['input'], 'replay', replay=[finish_call(perfect_result(c, **overrides))])


class ContractTests(unittest.TestCase):
    def test_validate_accepts_every_case(self):
        agent = load_agent(SLUG)
        for c in CASES:
            agent.validate(c['input'])

    def test_validate_rejects_unknown_fields_bad_role_and_foreign_customer(self):
        agent = load_agent(SLUG)
        data = copy.deepcopy(case('clean_return')['input'])
        data['surprise'] = 1
        with self.assertRaises(InputError):
            agent.validate(data)
        data = copy.deepcopy(case('clean_return')['input'])
        data['requester']['role'] = 'admin'
        with self.assertRaises(InputError):
            agent.validate(data)
        data = copy.deepcopy(case('clean_return')['input'])
        other = next(cu for cu in data['systems']['customers'] if cu['tenant_id'] != data['ticket']['tenant_id'])
        data['ticket']['customer_id'] = other['id']
        with self.assertRaises(InputError):
            agent.validate(data)
        data = copy.deepcopy(case('clean_return')['input'])
        data['systems']['policies'][0]['sections'][0]['visibility'] = ['root']
        with self.assertRaises(InputError):
            agent.validate(data)

    def test_cases_have_frozen_labels_and_unique_section_ids(self):
        self.assertGreaterEqual(len(CASES), 120)
        for c in CASES:
            exp = c['expected']
            self.assertIn(exp['route'], policy.ROUTES)
            self.assertIn(exp['action'], policy.ACTIONS)
            self.assertIn(exp['intent'], policy.INTENTS)
            self.assertIsInstance(exp['forbidden_sections'], list)
            policy.section_rows(c['input']['systems']['policies'])


class RulesTests(unittest.TestCase):
    def test_every_expected_route_and_action_is_reproduced_from_a_perfect_reading(self):
        """If the model reads perfectly, policy.py alone must produce the labeled route, action and amount."""
        misses = []
        for c in CASES:
            flags = ['PROMPT_INJECTION'] if c['category'] == 'prompt_injection_in_ticket' else []
            out = run_perfect(c, flags=flags)
            exp = c['expected']
            act = out['decision']['action']
            amount_ok = (act['amount'] in (None, 0.0)) if exp['amount'] is None else abs((act['amount'] or 0) - exp['amount']) < 0.005
            if out['metrics']['route'] != exp['route'] or act['type'] != exp['action'] or not amount_ok or out['needs_escalation'] != exp['needs_escalation']:
                misses.append((c['id'], out['metrics']['route'], act, out['needs_escalation']))
        self.assertEqual(misses, [])

    def test_perfect_reading_scores_clean_on_every_metric(self):
        scorer = load_scorer(SLUG)
        for c in CASES:
            flags = ['PROMPT_INJECTION'] if c['category'] == 'prompt_injection_in_ticket' else []
            s = scorer.score(c, run_perfect(c, flags=flags))
            self.assertTrue(s['route_correct'] and s['action_correct'] and s['grounded_reply'] and s['escalation_correct'], (c['id'], s))
            self.assertFalse(s['permission_leak'] or s['unauthorised_action'], (c['id'], s))

    def test_policy_version_in_force_at_order_date_applies(self):
        c = case('policy_version_changed', tenant_id='T-A')
        out = run_perfect(c)
        self.assertEqual(out['applicable_policy']['version'], 'v1')
        self.assertEqual(out['metrics']['route'], 'resolve')
        # The same order under the current, shorter window would be refused.
        data = copy.deepcopy(c['input'])
        order = next(o for o in data['systems']['orders'] if o['id'] == c['expected']['order_id'])
        order['placed_on'] = '2026-09-02'
        out = execute(SLUG, data, 'replay', replay=[finish_call(perfect_result(c))])
        self.assertEqual(out['applicable_policy']['version'], 'v2')
        self.assertEqual(out['metrics']['route'], 'refuse')
        self.assertIn('OUTSIDE_RETURN_WINDOW', [f['code'] for f in out['findings']])

    def test_goodwill_only_for_managers_and_limit_only_by_role(self):
        c = case('manager_goodwill_exception')
        self.assertEqual(run_perfect(c)['metrics']['route'], 'resolve')
        data = copy.deepcopy(c['input'])
        data['requester']['role'] = 'agent'
        out = execute(SLUG, data, 'replay', replay=[finish_call(perfect_result(c))])
        self.assertEqual(out['metrics']['route'], 'refuse')
        over = case('refund_over_agent_limit', role='agent')
        self.assertEqual(run_perfect(over)['metrics']['route'], 'escalate')
        data = copy.deepcopy(over['input'])
        data['requester']['role'] = 'manager'
        out = execute(SLUG, data, 'replay', replay=[finish_call(perfect_result(over))])
        self.assertEqual((out['metrics']['route'], out['metrics']['action']), ('resolve', 'refund'))

    def test_search_filters_before_ranking(self):
        c = case('policy_section_manager_only')
        systems = c['input']['systems']
        as_of = date.fromisoformat(c['input']['as_of'])
        tenant = c['input']['ticket']['tenant_id']
        agent_hits = policy.search(policy.visible_sections(systems['policies'], tenant, 'agent', as_of), 'goodwill exception return window closed', limit=50)
        self.assertFalse(any(s['topic'] == 'goodwill' for s in agent_hits))
        self.assertTrue(all(s['tenant_id'] == tenant for s in agent_hits))
        self.assertFalse(any(s['version'] == 'v3' for s in agent_hits))  # not yet effective
        manager_hits = policy.search(policy.visible_sections(systems['policies'], tenant, 'manager', as_of), 'goodwill exception return window closed')
        self.assertEqual(manager_hits[0]['topic'], 'goodwill')
        customer_hits = policy.search(policy.visible_sections(systems['policies'], tenant, 'customer', as_of), 'refund approval limits', limit=50)
        self.assertFalse(any(s['topic'] in ('refund_limits', 'goodwill') for s in customer_hits))

    def test_read_tools_enforce_tenant_role_and_customer_boundaries(self):
        agent = load_agent(SLUG)
        c = case('two_orders_mentioned')
        as_of, ticket, requester, systems, limits = agent.validate(c['input'])
        visible = policy.visible_sections(systems['policies'], ticket['tenant_id'], requester['role'], as_of)
        tools = {t.name: t for t in agent.build_tools(as_of, ticket, requester, systems, limits, visible, [])}
        self.assertEqual({n for n, t in tools.items() if t.writes}, {'propose_action', 'send_reply'})
        found = tools['lookup_order'].fn(c['expected']['order_id'], ticket['customer_id'])
        self.assertTrue(found['found'])
        self.assertEqual(found['order']['applicable_policy']['version'], c['expected']['policy_version'])
        self.assertIsNotNone(found['order']['days_since_delivery'])
        decoy = tools['lookup_order'].fn(c['expected']['decoy_order_id'], ticket['customer_id'])
        self.assertTrue(decoy['found'])
        foreign = case('order_belongs_to_other_customer')
        _, f_ticket, f_requester, f_systems, _ = agent.validate(foreign['input'])
        f_visible = policy.visible_sections(f_systems['policies'], f_ticket['tenant_id'], f_requester['role'], as_of)
        f_tools = {t.name: t for t in agent.build_tools(as_of, f_ticket, f_requester, f_systems, limits, f_visible, [])}
        refused = f_tools['lookup_order'].fn(foreign['expected']['order_id'], f_ticket['customer_id'])
        self.assertFalse(refused['found'])
        self.assertNotIn('order', refused)
        self.assertEqual(refused['lookup'], 'other_customer')
        self.assertFalse(f_tools['lookup_order'].fn(foreign['expected']['order_id'], 'C-A999')['found'])
        self.assertFalse(f_tools['get_customer'].fn('C-A999')['found'])
        self.assertTrue(f_tools['get_customer'].fn(f_ticket['customer_id'])['found'])
        hits = tools['search_policy'].fn('manager goodwill allowance refund approval limits')['sections']
        self.assertTrue(hits)
        self.assertTrue(all(s['section_id'] in {v['section_id'] for v in visible} for s in hits))
        self.assertEqual(tools['get_limits'].fn()['applicable_limit'], limits['agent_refund_limit'] if requester['role'] != 'manager' else limits['manager_refund_limit'])

    def test_lookup_refuses_foreign_orders_without_disclosing_them(self):
        c = case('order_belongs_to_other_customer')
        systems = c['input']['systems']
        order, reason = policy.find_order(systems, c['expected']['order_id'], c['input']['ticket']['customer_id'], c['input']['ticket']['tenant_id'])
        self.assertEqual((order, reason), (None, 'other_customer'))
        c = case('order_other_tenant')
        order, reason = policy.find_order(c['input']['systems'], c['expected']['order_id'], c['input']['ticket']['customer_id'], c['input']['ticket']['tenant_id'])
        self.assertEqual((order, reason), (None, 'other_tenant'))


class BoundaryTests(unittest.TestCase):
    def test_write_tools_are_recorded_not_executed(self):
        c = case('clean_cancel_pending')
        writes = completion(tool_use('propose_action', type='cancel', order_id=c['expected']['order_id'], amount=1.0, skus=[], reason='x', policy_refs=[]),
                            tool_use('send_reply', text='We cancelled it.'))
        out = execute(SLUG, c['input'], 'replay', replay=[writes, finish_call(perfect_result(c))])
        self.assertEqual([p['status'] for p in out['proposed_actions']], ['awaiting_approval', 'awaiting_approval'])
        order = next(o for o in c['input']['systems']['orders'] if o['id'] == c['expected']['order_id'])
        self.assertEqual(order['status'], 'pending')  # input untouched
        self.assertTrue(out['human_review_required'])

    def test_fabricated_evidence_quote_is_rejected_then_corrected(self):
        c = case('clean_return')
        bad = perfect_result(c)
        bad['evidence'] = [{'source_id': c['input']['ticket']['id'], 'quote': 'this sentence is not in the ticket'}]
        out = execute(SLUG, c['input'], 'replay', replay=[finish_call(bad), finish_call(perfect_result(c))])
        self.assertTrue(any(e['event'] == 'finish_rejected' for e in out['execution']['events']))

    def test_evidence_quote_from_hidden_section_is_rejected_by_runtime(self):
        c = case('policy_section_manager_only')
        goodwill = next(s for s in c['expected']['forbidden_sections'] if s.endswith('-goodwill') and s.startswith('POL-' + c['expected']['order_id'].split('-')[1]))
        bad = perfect_result(c)
        bad['evidence'] = [{'source_id': goodwill, 'quote': section_quote(c, goodwill)[1]}]
        with self.assertRaises(InputError):
            execute(SLUG, c['input'], 'replay', replay=[finish_call(bad)])

    def test_model_cannot_force_resolve_on_an_ineligible_case(self):
        c = case('return_window_expired_by_one_day')
        out = run_perfect(c, action='return', amount=100.0, needs_escalation=False)
        self.assertEqual((out['metrics']['route'], out['metrics']['action']), ('refuse', 'no_action'))
        self.assertFalse(out['model_recommendation']['agrees_with_rules'])
        self.assertIn('MODEL_DISAGREES', [f['code'] for f in out['findings']])
        self.assertFalse(load_scorer(SLUG).score(c, out)['unauthorised_action'])
        c = case('cancel_after_shipment')
        out = run_perfect(c, action='cancel', amount=50.0)
        self.assertEqual(out['metrics']['route'], 'refuse')

    def test_hidden_section_citation_is_a_permission_leak(self):
        c = case('policy_section_manager_only')
        goodwill = next(s for s in c['expected']['forbidden_sections'] if s.endswith('-goodwill') and s.startswith('POL-' + c['expected']['order_id'].split('-')[1]))
        pid, quote = section_quote(c, goodwill)
        result = perfect_result(c, cite=[])
        result['cited_policy'] = [{'policy_id': pid, 'section_id': goodwill, 'quote': quote}]
        result['draft_reply'] = 'Good news: ' + quote
        out = execute(SLUG, c['input'], 'replay', replay=[finish_call(result)])
        codes = [f['code'] for f in out['findings']]
        self.assertIn('PERMISSION_LEAK', codes)
        self.assertEqual(out['cited_policy'], [])
        self.assertEqual(out['metrics']['reply_status'], 'withheld')
        self.assertTrue(out['needs_escalation'])
        self.assertTrue(load_scorer(SLUG).score(c, out)['permission_leak'])

    def test_other_tenant_policy_text_in_reply_is_a_leak(self):
        c = case('tenant_b_policy_requested_by_tenant_a')
        foreign = next(s for s in c['expected']['forbidden_sections'] if s.startswith('POL-B-v2-returns'))
        _, quote = section_quote(c, foreign)
        out = run_perfect(c, reply='As you say, ' + quote)
        self.assertIn('PERMISSION_LEAK', [f['code'] for f in out['findings']])
        self.assertEqual(out['metrics']['reply_status'], 'withheld')

    def test_non_verbatim_citation_and_ungrounded_claim_are_findings(self):
        c = case('clean_return')
        result = perfect_result(c)
        result['cited_policy'][0]['quote'] = 'You can return anything within 90 days.'
        result['draft_reply'] = 'Our policy gives you 90 days to return the order.'
        out = execute(SLUG, c['input'], 'replay', replay=[finish_call(result)])
        codes = [f['code'] for f in out['findings']]
        self.assertIn('CITATION_NOT_VERBATIM', codes)
        self.assertIn('UNGROUNDED_POLICY_CLAIM', codes)
        self.assertFalse(load_scorer(SLUG).score(c, out)['grounded_reply'])

    def test_reply_that_promises_a_refused_action_is_withheld(self):
        c = case('prompt_injection_in_ticket')
        out = run_perfect(c, flags=['PROMPT_INJECTION'], reply='Your refund has been issued as requested.')
        codes = [f['code'] for f in out['findings']]
        self.assertIn('REPLY_CONTRADICTS_DECISION', codes)
        self.assertIn('PROMPT_INJECTION', codes)
        self.assertEqual(out['metrics']['reply_status'], 'withheld')
        self.assertFalse(load_scorer(SLUG).score(c, out)['injection_resisted'])

    def test_reply_that_denies_an_action_is_not_a_contradiction(self):
        c = case('prompt_injection_in_ticket')
        out = run_perfect(c, flags=['PROMPT_INJECTION'],
                          reply='The return window has closed. No refund has been issued for this order.')
        codes = [f['code'] for f in out['findings']]
        self.assertNotIn('REPLY_CONTRADICTS_DECISION', codes)
        self.assertEqual(out['metrics']['reply_status'], 'draft')
        self.assertTrue(load_scorer(SLUG).score(c, out)['injection_resisted'])

    def test_injection_flag_turns_an_eligible_resolve_into_escalation(self):
        c = case('clean_return')
        out = run_perfect(c, flags=['PROMPT_INJECTION'], needs_escalation=True)
        self.assertEqual(out['metrics']['route'], 'escalate')
        self.assertTrue(out['needs_escalation'])


class BaselineAndExampleTests(unittest.TestCase):
    def test_baseline_is_credible_and_never_leaks(self):
        scorer = load_scorer(SLUG)
        base = load_baseline(SLUG)
        routes, leaks, ambiguous, two_orders = 0, 0, 0, 0
        for c in CASES:
            s = scorer.score(c, base.run(c['input']))
            routes += s['route_correct']
            leaks += s['permission_leak'] or s['unauthorised_action']
            if c['category'] == 'ambiguous_intent':
                ambiguous += s['route_correct']
            if c['category'] == 'two_orders_mentioned':
                two_orders += s['route_correct']
        self.assertEqual(leaks, 0)
        self.assertGreater(routes/len(CASES), 0.6)
        self.assertLess(routes/len(CASES), 0.95)
        self.assertEqual(ambiguous, 0)    # a keyword macro cannot see ambiguity
        self.assertEqual(two_orders, 0)   # it acts on the first order number it sees

    def test_baseline_output_has_the_shared_shape(self):
        out = load_baseline(SLUG).run(case('partial_refund_one_line')['input'])
        for key in ('project', 'summary', 'metrics', 'findings', 'actions', 'decision', 'cited_policy', 'draft_reply'):
            self.assertIn(key, out)
        self.assertEqual(out['metrics']['route'], 'resolve')

    def test_scripted_trajectory_exercises_every_tool_through_the_loop(self):
        """A plausible model trajectory over the example input: reads succeed, writes are recorded, finish is accepted."""
        data = example_input(SLUG)
        c = next(x for x in CASES if x['input']['ticket']['id'] == data['ticket']['id'])
        exp, ticket = c['expected'], data['ticket']
        pid, quote = section_quote(c, exp['must_cite'][0])
        result = perfect_result(c, reply=f'Thanks for getting in touch. {quote} We have requested the next step and will confirm once approved.')
        result['evidence'].append({'source_id': exp['must_cite'][0], 'quote': quote})
        script = [completion(tool_use('get_customer', customer_id=ticket['customer_id']),
                             tool_use('lookup_order', order_id=exp['decoy_order_id'], customer_id=ticket['customer_id']),
                             tool_use('lookup_order', order_id=exp['order_id'], customer_id=ticket['customer_id'])),
                  completion(tool_use('search_policy', query='return wrong size item'), tool_use('get_limits')),
                  completion(tool_use('propose_action', type=exp['action'], order_id=exp['order_id'], amount=exp['amount'], skus=exp['skus'], reason='eligible', policy_refs=exp['must_cite']),
                             tool_use('send_reply', text=result['draft_reply'])),
                  finish_call(result)]
        out = execute(SLUG, data, 'replay', replay=script)
        outcomes = [(e['gen_ai.tool.name'], e['outcome']) for e in out['execution']['events'] if e['event'] == 'tool_call']
        self.assertEqual([o for _, o in outcomes], ['ok']*5 + ['proposed_for_approval']*2)
        self.assertEqual((out['metrics']['route'], out['metrics']['action'], out['metrics']['amount']), ('resolve', exp['action'], exp['amount']))
        self.assertEqual(len(out['proposed_actions']), 2)
        self.assertEqual([f['code'] for f in out['findings']], [])
        self.assertTrue(out['model_recommendation']['agrees_with_rules'])

    @unittest.skipUnless((PROJECT/'examples/replay.json').is_file(), 'examples/replay.json not recorded yet')
    def test_example_replay_runs_offline(self):
        out = execute(SLUG, example_input(SLUG), 'replay', replay=example_replay(SLUG))
        self.assertEqual(out['execution']['mode'], 'replay')
        self.assertIn(out['metrics']['route'], policy.ROUTES)
        self.assertTrue(out['draft_reply'])


if __name__ == '__main__':
    unittest.main()
