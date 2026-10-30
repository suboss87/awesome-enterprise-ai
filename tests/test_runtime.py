"""Shared runtime tests: agent loop, approval gate, finish validation, replay, cost."""
import json
import unittest

from enterprise_ai.agent import Agent, Tool, Trace
from enterprise_ai.common import InputError
from enterprise_ai.llm import ReplayProvider, RecordingProvider, estimate_cost, _strict


def completion(*blocks, stop='tool_use', model='claude-opus-5-5'):
    return {'content': list(blocks), 'stop_reason': stop, 'model': model, 'response_id': 'r1',
            'usage': {'input_tokens': 1000, 'output_tokens': 100, 'cache_read_input_tokens': 0}}


def call(name, **kwargs):
    return {'type': 'tool_use', 'id': f'call_{name}_{len(json.dumps(kwargs))}', 'name': name, 'input': kwargs}


SCHEMA = {'type': 'object', 'properties': {'answer': {'type': 'string'},
          'evidence': {'type': 'array', 'items': {'type': 'object', 'properties': {'source_id': {'type': 'string'}, 'quote': {'type': 'string'}}}}}}


class ScriptedProvider:
    """Records the requests it sees and answers from a script."""
    name = 'scripted'
    model = 'test'

    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def complete(self, system, messages, tools):
        self.requests.append({'system': system, 'messages': json.loads(json.dumps(messages)), 'tools': tools})
        return self.script.pop(0)


def make_agent(executed):
    def read(key):
        return {'key': key, 'value': 42}

    def write(amount):
        executed.append(amount)
        return 'done'
    return Agent('t', 'system', [Tool('read', 'read', {'type': 'object', 'properties': {'key': {'type': 'string'}}}, read),
                                 Tool('pay', 'pay', {'type': 'object', 'properties': {'amount': {'type': 'number'}}}, write, writes=True)], SCHEMA)


class AgentLoopTests(unittest.TestCase):
    def test_write_tool_is_proposed_not_executed(self):
        executed = []
        provider = ScriptedProvider([completion(call('read', key='a'), call('pay', amount=5)),
                                     completion(call('finish', answer='ok', evidence=[]))])
        out = make_agent(executed).run('task', provider, Trace('t', 'scripted'))
        self.assertEqual(executed, [])
        self.assertEqual(out['proposed_actions'], [{'tool': 'pay', 'input': {'amount': 5}, 'status': 'awaiting_approval'}])
        results = provider.requests[1]['messages'][-1]['content']
        self.assertEqual(len(results), 2)
        self.assertIn('NOT executed', results[1]['content'])
        self.assertEqual(out['result']['answer'], 'ok')
        self.assertEqual(out['trace']['model_calls'], 2)
        self.assertEqual(out['trace']['tool_calls'], 2)
        self.assertAlmostEqual(out['trace']['cost_usd'], 2*(1000*4 + 100*20)/1e6)

    def test_invalid_tool_input_is_reported_back(self):
        provider = ScriptedProvider([completion(call('read', wrong='a')), completion(call('finish', answer='x', evidence=[]))])
        make_agent([]).run('task', provider, Trace('t', 'scripted'))
        result = provider.requests[1]['messages'][-1]['content'][0]
        self.assertTrue(result['is_error'])
        self.assertIn('Invalid input', result['content'])

    def test_finish_rejected_when_schema_or_evidence_wrong(self):
        provider = ScriptedProvider([completion(call('finish', answer='x', evidence=[{'source_id': 'doc', 'quote': 'not there'}])),
                                     completion(call('finish', answer='x', evidence=[{'source_id': 'doc', 'quote': 'real text'}]))])
        out = make_agent([]).run('task', provider, Trace('t', 'scripted'), sources={'doc': 'some real text here'})
        self.assertEqual(out['steps'], 2)
        self.assertIn('finish rejected', provider.requests[1]['messages'][-1]['content'][0]['content'])

    def test_agent_specific_result_check_rejects_and_lets_the_model_correct(self):
        def check(result):
            if result['answer'] == 'leak':
                raise InputError('answer must not be leak')
        agent = make_agent([])
        agent.result_check = check
        provider = ScriptedProvider([completion(call('finish', answer='leak', evidence=[])), completion(call('finish', answer='safe', evidence=[]))])
        out = agent.run('task', provider, Trace('t', 'scripted'))
        self.assertEqual(out['result']['answer'], 'safe')
        self.assertIn('must not be leak', provider.requests[1]['messages'][-1]['content'][0]['content'])

    def test_prose_without_finish_is_nudged_then_fails_at_step_limit(self):
        agent = make_agent([])
        agent.max_steps = 2
        provider = ScriptedProvider([completion({'type': 'text', 'text': 'Here is my answer.'}, stop='end_turn'),
                                     completion({'type': 'text', 'text': 'Still prose.'}, stop='end_turn')])
        with self.assertRaises(InputError):
            agent.run('task', provider, Trace('t', 'scripted'))
        self.assertIn('finish tool', provider.requests[1]['messages'][-1]['content'][0]['text'])

    def test_refusal_stops_the_run(self):
        provider = ScriptedProvider([completion(stop='refusal')])
        with self.assertRaises(InputError):
            make_agent([]).run('task', provider, Trace('t', 'scripted'))

    def test_unknown_tool_name_is_handled(self):
        provider = ScriptedProvider([completion(call('delete_everything')), completion(call('finish', answer='x', evidence=[]))])
        out = make_agent([]).run('task', provider, Trace('t', 'scripted'))
        self.assertEqual(out['proposed_actions'], [])
        self.assertEqual(provider.requests[1]['messages'][-1]['content'][0]['content'], 'Unknown tool')


class ReplayTests(unittest.TestCase):
    def test_replay_rejects_stale_recording(self):
        provider = ReplayProvider([completion(call('no_such_tool'))])
        with self.assertRaises(InputError):
            make_agent([]).run('task', provider, Trace('t', 'replay'))

    def test_recording_wraps_live_provider(self):
        inner = ScriptedProvider([completion(call('finish', answer='x', evidence=[]))])
        recording = RecordingProvider(inner)
        make_agent([]).run('task', recording, Trace('t', 'scripted'))
        self.assertEqual(len(recording.recording), 1)
        replay = ReplayProvider(recording.recording)
        out = make_agent([]).run('task', replay, Trace('t', 'replay'))
        self.assertEqual(out['result']['answer'], 'x')


class SchemaTests(unittest.TestCase):
    def test_strict_adds_required_and_closes_objects(self):
        schema = _strict({'type': 'object', 'properties': {'a': {'type': 'string'}, 'b': {'type': 'object', 'properties': {'c': {'type': 'number'}}}}})
        self.assertEqual(schema['required'], ['a', 'b'])
        self.assertFalse(schema['additionalProperties'])
        self.assertFalse(schema['properties']['b']['additionalProperties'])

    def test_cost_is_none_for_unknown_model(self):
        self.assertIsNone(estimate_cost('mystery', {'input_tokens': 1, 'output_tokens': 1}))


if __name__ == '__main__':
    unittest.main()
