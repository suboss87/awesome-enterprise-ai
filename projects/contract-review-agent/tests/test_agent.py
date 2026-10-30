"""Contract Review Agent: rules, generator, baseline, write boundary, grounding, injection, replay."""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from enterprise_ai.agent import Trace  # noqa: E402
from enterprise_ai.common import InputError  # noqa: E402
from enterprise_ai.llm import ReplayProvider  # noqa: E402

SLUG = 'contract-review-agent'
PROJECT = ROOT/'projects'/SLUG


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent = _load('contract_agent_t', PROJECT/'agent.py')
playbook = agent.playbook
baseline = _load('contract_baseline_t', PROJECT/'baseline.py')
scorer = _load('contract_score_t', PROJECT/'evals/score.py')
generator = _load('contract_generator_t', PROJECT/'evals/generate_cases.py')
CASES = [json.loads(line) for line in (PROJECT/'evals/cases.jsonl').read_text().splitlines() if line.strip()]


def case(category, index=0):
    return [c for c in CASES if c['category'] == category][index]


def completion(*blocks):
    return {'content': list(blocks), 'stop_reason': 'tool_use', 'model': 'test', 'response_id': 'x',
            'usage': {'input_tokens': 10, 'output_tokens': 5, 'cache_read_input_tokens': 0}}


def tool_use(name, **kwargs):
    return {'type': 'tool_use', 'id': f'call_{name}_{len(str(kwargs))}', 'name': name, 'input': kwargs}


def finish_call(result):
    return completion(tool_use('finish', **result))


def perfect_result(c, terms=None, flags=None, route=None, evidence=None):
    """A finish payload built from the case's reference terms: what a perfect reader would submit."""
    exp = c['expected']
    quote = exp['injection'] or exp['reference_terms'][0]['quote']
    return {'terms': copy.deepcopy(exp['reference_terms'] if terms is None else terms),
            'flags': (['PROMPT_INJECTION'] if exp['injection'] else []) if flags is None else flags,
            'recommended_route': route or exp['route'], 'rationale': 'Per playbook.',
            'evidence': evidence if evidence is not None else [{'source_id': c['input']['contract']['id'], 'quote': quote}]}


def run(c, completions, data=None):
    trace = Trace(SLUG, 'replay')
    provider = ReplayProvider(completions)
    out = agent.run(copy.deepcopy(data or c['input']), provider, trace)
    out['events'] = trace.events
    return out


def run_perfect(c, **overrides):
    return run(c, [finish_call(perfect_result(c, **overrides))])


def position(c, topic):
    return next(p for p in c['input']['playbook']['positions'] if p['topic'] == topic)


class RulesTests(unittest.TestCase):
    def test_perfect_reader_reproduces_every_label(self):
        """If the model reads perfectly, playbook.py alone produces the labeled route, deviations and codes."""
        misses = []
        for c in CASES:
            out = run_perfect(c)
            exp = c['expected']
            codes = {f['code'] for f in out['findings']}
            s = scorer.score(c, out)
            if (out['route'], sorted(d['topic'] for d in out['deviations'])) != (exp['route'], exp['deviations']) \
                    or not set(exp['must_flag']) <= codes or not s['terms_grounded'] or s['unsafe_approve']:
                misses.append((c['id'], out['route'], sorted(codes)))
        self.assertEqual(misses, [])

    def test_thresholds_and_risk_tiers(self):
        nda = {p['topic']: p for p in generator.NDA_PLAYBOOK['positions']}
        msa = {p['topic']: p for p in generator.MSA_PLAYBOOK['positions']}
        sev = playbook._severity
        self.assertIsNone(sev('term', 24, nda['term']['rule'], None))
        self.assertEqual(sev('term', 36, nda['term']['rule'], None), 'acceptable')
        self.assertEqual(sev('term', 37, nda['term']['rule'], None), 'counsel')
        self.assertEqual(sev('term', 'perpetual', nda['term']['rule'], None), 'counsel')
        cap = msa['liability_cap']['rule']
        self.assertEqual([sev('liability_cap', playbook.parse_value('liability_cap', v), cap, None) for v in ('2', '1', '0.5', '0.25', 'uncapped')],
                         [None, 'acceptable', 'counsel', 'walk_away', None])
        renewal = nda['auto_renewal']['rule']
        self.assertEqual([sev('auto_renewal', v, renewal, None) for v in ('none', 30, 29, 'no_notice')], [None, None, 'counsel', 'counsel'])
        self.assertEqual(sev('residuals', 'present', nda['residuals']['rule'], None), 'walk_away')
        self.assertEqual(sev('venue', 'singapore', nda['venue']['rule'], 'new york'), 'counsel')
        self.assertIsNone(sev('venue', 'new york', nda['venue']['rule'], 'new york'))
        self.assertEqual(sev('governing_law', 'texas', nda['governing_law']['rule'], None), 'counsel')

    def test_value_forms_and_jurisdictions(self):
        self.assertEqual(playbook.parse_value('term', '60'), 60)
        self.assertEqual(playbook.jurisdiction('the State of New York'), 'new york')
        self.assertEqual(playbook.jurisdiction('English'), 'england and wales')
        for topic, value in (('term', 'five years'), ('mutuality', 'mostly'), ('liability_cap', 'NaN'), ('auto_renewal', 'yes')):
            with self.assertRaises(InputError):
                playbook.parse_value(topic, value)

    def test_clause_map_reads_every_layout(self):
        refs = {c['expected']['layout']: [s['ref'] for s in playbook.clauses(c['input']['contract']['text'])] for c in CASES[:4]}
        self.assertIn('3', refs['numbered'])
        self.assertIn('SECTION 3. TERM', next(s['text'] for s in playbook.clauses(CASES[0]['input']['contract']['text']) if s['ref'] == '3'))
        self.assertIn('3(a)', refs['lettered'])
        self.assertIn('1.1', refs['definitions_first'])
        self.assertEqual(playbook.normalize_ref('Section 3(a).'), '3(a)')

    def test_two_different_values_for_one_term_are_inconsistent(self):
        c = case('term_inconsistent')
        out = run_perfect(c)
        dev = next(d for d in out['deviations'] if d['topic'] == 'term')
        self.assertIn(' / ', dev['found'])
        self.assertEqual(out['route'], 'counsel_review')
        self.assertIn('INCONSISTENT_TERM', [f['code'] for f in out['findings']])

    def test_missing_required_clause_routes_to_counsel(self):
        c = case('msa_missing_clause')
        out = run_perfect(c)
        self.assertEqual(out['deviations'][0]['found'], 'missing')
        self.assertIn('MISSING_CLAUSE', [f['code'] for f in out['findings']])


class GeneratorTests(unittest.TestCase):
    def test_generator_is_deterministic_and_matches_committed_cases(self):
        first, second = generator.build_cases(), generator.build_cases()
        self.assertEqual(first, second)
        self.assertEqual(first, CASES)

    def test_case_set_shape(self):
        categories = {c['category'] for c in CASES}
        self.assertTrue(110 <= len(CASES) <= 130)
        self.assertTrue(14 <= len(categories) <= 18)
        self.assertEqual(len({c['id'] for c in CASES}), len(CASES))
        self.assertEqual({c['expected']['layout'] for c in CASES}, set(generator.LAYOUTS))
        for c in CASES:
            agent.validate(c['input'])
            for term in c['expected']['reference_terms']:
                self.assertIn(term['quote'], c['input']['contract']['text'], c['id'])

    def test_labels_cover_all_three_routes(self):
        routes = {c['expected']['route'] for c in CASES}
        self.assertEqual(routes, set(playbook.ROUTES))


class BaselineTests(unittest.TestCase):
    def test_baseline_reads_standard_contracts_and_never_releases_off_playbook_text(self):
        for c in CASES:
            out = baseline.run(c['input'])
            s = scorer.score(c, out)
            if c['category'] in ('clean_standard_nda', 'our_paper_unchanged', 'msa_clean', 'acceptable_fallback'):
                self.assertTrue(s['route_correct'], c['id'])
            self.assertNotEqual(s['redline_from_playbook_only'], False, c['id'])

    def test_baseline_misses_the_hard_cases_a_keyword_cannot_see(self):
        """Documented gaps: the title says mutual, the hiring ban avoids 'solicit', the second term is never read."""
        for category in ('mutual_mislabeled_one_way', 'term_inconsistent'):
            self.assertEqual(baseline.run(case(category)['input'])['route'], 'approve_standard', category)
        self.assertEqual(baseline.run(case('non_solicit_in_confidentiality', 1)['input'])['route'], 'approve_standard')
        self.assertEqual(baseline.run(case('residuals_in_definitions', 0)['input'])['route'], 'walk_away')  # "unaided memory" is a keyword


class BoundaryTests(unittest.TestCase):
    def test_model_cannot_force_approve_standard(self):
        c = case('residuals_in_definitions')
        out = run_perfect(c, route='approve_standard')
        self.assertEqual(out['route'], 'walk_away')
        self.assertFalse(out['model_recommendation']['agrees_with_rules'])
        self.assertIn('MODEL_DISAGREES', [f['code'] for f in out['findings']])
        self.assertFalse(scorer.score(c, out)['unsafe_approve'])

    def test_unsafe_approve_is_zero_for_a_perfect_reader_and_counted_otherwise(self):
        c = case('mutual_mislabeled_one_way')
        misread = [dict(t, value='mutual') if t['topic'] == 'mutuality' else t for t in c['expected']['reference_terms']]
        out = run_perfect(c, terms=misread)
        self.assertEqual(out['route'], 'approve_standard')
        self.assertTrue(scorer.score(c, out)['unsafe_approve'])  # the metric catches a misread
        self.assertFalse(scorer.score(c, run_perfect(c))['unsafe_approve'])

    def test_ungrounded_term_is_flagged_dropped_and_escalated(self):
        c = case('clean_standard_nda')
        terms = copy.deepcopy(c['expected']['reference_terms'])
        terms.append({'topic': 'residuals', 'value': 'present', 'quote': 'Recipient may use residual knowledge for any purpose.'})
        for t in terms:
            if t['topic'] == 'term':
                t['quote'] = 'obligations continue for twenty-four months'  # paraphrase, not in the contract
        out = run_perfect(c, terms=terms)
        codes = [f['code'] for f in out['findings']]
        self.assertIn('UNGROUNDED_TERM', codes)
        self.assertIn('MISSING_CLAUSE', codes)  # the required term no longer has a grounded value
        self.assertEqual(out['route'], 'counsel_review')
        self.assertEqual(out['metrics']['ungrounded_terms'], 2)
        self.assertFalse(scorer.score(c, out)['terms_grounded'])

    def test_redline_off_playbook_is_withheld_and_fallback_is_released(self):
        c = case('non_solicit_in_confidentiality')
        ref = next(d['clause_ref'] for d in run_perfect(c)['deviations'] if d['topic'] == 'non_solicit')
        own_words = completion(tool_use('draft_redline', topic='non_solicit', clause_ref=ref, replacement_text='Delete the hiring restriction.'))
        fallback = completion(tool_use('draft_redline', topic='non_solicit', clause_ref=ref, replacement_text=position(c, 'non_solicit')['fallback']))
        unneeded = completion(tool_use('draft_redline', topic='term', clause_ref=ref, replacement_text=position(c, 'term')['fallback']))
        out = run(c, [own_words, fallback, unneeded, finish_call(perfect_result(c))])
        self.assertEqual([r['status'] for r in out['redlines']], ['withheld', 'draft', 'withheld'])
        codes = [f['code'] for f in out['findings']]
        self.assertIn('REDLINE_NOT_FROM_PLAYBOOK', codes)
        self.assertIn('UNNEEDED_REDLINE', codes)
        released = next(a for a in out['actions'] if a['action'] == 'send_redline')['redlines']
        self.assertEqual([r['replacement_text'] for r in released], [position(c, 'non_solicit')['fallback']])
        self.assertTrue(scorer.score(c, out)['redline_from_playbook_only'])

    def test_write_tools_are_recorded_not_executed(self):
        c = case('law_venue_mismatch')
        before = copy.deepcopy(c['input'])
        writes = completion(tool_use('submit_to_legal_queue', route='approve_standard', note='Looks fine.'),
                            tool_use('draft_redline', topic='venue', clause_ref='', replacement_text=position(c, 'venue')['fallback']))
        out = run(c, [writes, finish_call(perfect_result(c))])
        self.assertEqual([p['status'] for p in out['proposed_actions']], ['awaiting_approval', 'awaiting_approval'])
        self.assertEqual(out['route'], 'counsel_review')  # the queued route came from the rules, not the proposal
        self.assertEqual(c['input'], before)
        self.assertTrue(out['human_review_required'])

    def test_fabricated_evidence_quote_is_rejected_then_corrected(self):
        c = case('clean_standard_nda')
        bad = perfect_result(c, evidence=[{'source_id': c['input']['contract']['id'], 'quote': 'This NDA was approved by counsel.'}])
        out = run(c, [finish_call(bad), finish_call(perfect_result(c))])
        self.assertTrue(any(e['event'] == 'finish_rejected' for e in out['events']))
        self.assertEqual(out['route'], 'approve_standard')

    def test_injection_flag_escalates_and_never_clears(self):
        c = case('prompt_injection_in_clause')
        out = run_perfect(c)
        self.assertEqual(out['route'], 'counsel_review')
        self.assertIn('PROMPT_INJECTION', [f['code'] for f in out['findings']])
        self.assertTrue(scorer.score(c, out)['injection_flagged'])
        self.assertIn(c['expected']['injection'], out['evidence'][0]['quote'])
        missed = run_perfect(c, flags=[])
        self.assertFalse(scorer.score(c, missed)['injection_flagged'])
        walk = case('residuals_in_definitions')
        self.assertEqual(run_perfect(walk, flags=['PROMPT_INJECTION'])['route'], 'walk_away')

    def test_tools_read_clauses_and_mirror_the_final_rules(self):
        c = case('law_venue_mismatch')
        contract, positions, _ = agent.validate(c['input'])
        tools = {t.name: t for t in agent.build_tools(contract, positions)}
        self.assertEqual({n for n, t in tools.items() if t.writes}, {'draft_redline', 'submit_to_legal_queue'})
        ref = playbook.clauses(contract['text'])[1]['ref']
        self.assertTrue(tools['get_clause'].fn(f'Section {ref}')['found'])
        self.assertFalse(tools['get_clause'].fn('99')['found'])
        self.assertTrue(tools['search_clauses'].fn('dispute jurisdiction')['clauses'])
        self.assertEqual(tools['get_playbook_position'].fn('venue')['fallback'], position(c, 'venue')['fallback'])
        checked = tools['compare_to_playbook'].fn(c['expected']['reference_terms'])
        self.assertEqual((checked['route'], [d['topic'] for d in checked['deviations']]), (c['expected']['route'], c['expected']['deviations']))

    def test_input_contract_is_strict(self):
        good = case('clean_standard_nda')['input']
        for mutate in (lambda d: d.update(surprise=1), lambda d: d['contract'].update(paper='mine'),
                       lambda d: d['requester'].update(role='ceo'), lambda d: d['playbook'].update(contract_type='MSA'),
                       lambda d: d['playbook']['positions'].pop(0),
                       lambda d: d['playbook']['positions'][1]['rule'].update(max_months='36'),
                       lambda d: d['contract'].update(text='No numbered clauses here at all.')):
            data = copy.deepcopy(good)
            mutate(data)
            with self.assertRaises(InputError):
                agent.validate(data)


class ExampleTests(unittest.TestCase):
    def test_example_is_a_their_paper_nda_with_two_deviations(self):
        data = json.loads((PROJECT/'examples/input.json').read_text())
        contract, _, _ = agent.validate(data)
        self.assertEqual((contract['type'], contract['paper']), ('NDA', 'theirs'))
        label = next(c for c in CASES if c['input'] == data)['expected']
        self.assertEqual(len(label['deviations']), 2)
        self.assertEqual(baseline.run(data)['route'], 'counsel_review')


if __name__ == '__main__':
    unittest.main()
