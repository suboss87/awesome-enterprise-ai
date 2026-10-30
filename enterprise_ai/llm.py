"""Model providers behind one small interface.

Canonical message shape (Anthropic-like) used by the agent loop:
  {'role': 'user'|'assistant', 'content': [block, ...]}
  block: {'type': 'text', 'text': str}
       | {'type': 'tool_use', 'id': str, 'name': str, 'input': dict}
       | {'type': 'tool_result', 'tool_use_id': str, 'content': str, 'is_error': bool}

Each provider returns a Completion:
  {'content': [block, ...], 'stop_reason': 'end_turn'|'tool_use'|'max_tokens'|'refusal',
   'model': str, 'response_id': str, 'usage': {'input_tokens': int, 'output_tokens': int,
   'cache_read_input_tokens': int}}

Only the standard library is used. Keys come from the environment and never
appear in traces, results or error messages.
"""
import json
import os
import time
import urllib.error
import urllib.request

from .common import InputError, loads

ANTHROPIC_DEFAULT_MODEL = 'claude-opus-5-5'
OPENAI_DEFAULT_MODEL = 'gpt-5.5'

# USD per million tokens (input, output, cache read). Unknown models cost None.
PRICES = {
    'claude-opus-5-5': (4.00, 20.00, 0.20),
    'claude-sonnet-5-5': (2.00, 10.00, 0.20),
    'claude-haiku-4-5': (1.00, 5.00, 0.10),
    'gpt-5.5': (5.00, 30.00, 0.50),   # list price 2026-08; dated snapshots match by prefix
}


def price_for(model):
    model = str(model or '')
    for key in sorted(PRICES, key=len, reverse=True):
        if model == key or model.startswith(key + '-'):
            return PRICES[key]
    return None


def estimate_cost(model, usage):
    price = price_for(model)
    if not price or not usage:
        return None
    inp, out, cached = price
    fresh = max(0, usage.get('input_tokens', 0) - usage.get('cache_read_input_tokens', 0))
    return round((fresh*inp + usage.get('cache_read_input_tokens', 0)*cached + usage.get('output_tokens', 0)*out)/1e6, 6)


class ProviderError(InputError):
    """The provider failed or returned something unusable. Never carries the key."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError('Provider redirect rejected; credentials are not forwarded')


def _post(url, headers, body, timeout):
    data = json.dumps(body, allow_nan=False).encode()
    request = urllib.request.Request(url, data, {'Content-Type': 'application/json', **headers})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            raw = response.read(5_000_001)
    except urllib.error.HTTPError as exc:
        detail = ''
        try:
            detail = loads(exc.read(20000)).get('error', {}).get('message', '')[:300]
        except Exception:  # noqa: BLE001 - diagnostic only
            pass
        raise ProviderError(f'Provider returned HTTP {exc.code}: {detail}') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProviderError('Provider unavailable or timed out') from None
    if len(raw) > 5_000_000:
        raise ProviderError('Provider response exceeds 5 MB')
    return loads(raw)


def _strict(schema):
    """Tools use strict schemas: every property required, no extras."""
    schema = json.loads(json.dumps(schema))
    if schema.get('type') == 'object':
        schema['additionalProperties'] = False
        schema['required'] = list(schema.get('properties', {}))
        for value in schema.get('properties', {}).values():
            _strict_inplace(value)
    return schema


def _strict_inplace(schema):
    if schema.get('type') == 'object':
        schema['additionalProperties'] = False
        schema['required'] = list(schema.get('properties', {}))
        for value in schema.get('properties', {}).values():
            _strict_inplace(value)
    elif schema.get('type') == 'array' and isinstance(schema.get('items'), dict):
        _strict_inplace(schema['items'])


class Provider:
    name = 'abstract'
    model = None
    timeout = 180

    def complete(self, system, messages, tools):
        raise NotImplementedError


class AnthropicProvider(Provider):
    name = 'anthropic'

    def __init__(self, model=None, effort='medium', max_tokens=16000):
        self.model = model or os.environ.get('ANTHROPIC_MODEL', ANTHROPIC_DEFAULT_MODEL)
        self.effort = effort
        self.max_tokens = max_tokens

    def _headers(self):
        key = os.environ.get('ANTHROPIC_API_KEY')
        if not key:
            raise ProviderError('Set ANTHROPIC_API_KEY to use the Anthropic provider')
        return {'x-api-key': key, 'anthropic-version': '2023-06-01'}

    def complete(self, system, messages, tools):
        body = {'model': self.model, 'max_tokens': self.max_tokens, 'system': system,
                'messages': messages,
                'tools': [{'name': t['name'], 'description': t['description'],
                           'input_schema': _strict(t['input_schema']), 'strict': True} for t in tools],
                'output_config': {'effort': self.effort}}
        response = _post('https://api.anthropic.com/v1/messages', self._headers(), body, self.timeout)
        if response.get('type') != 'message':
            raise ProviderError('Unexpected provider response type')
        content = []
        for block in response.get('content', []):
            if block.get('type') == 'text':
                content.append({'type': 'text', 'text': block.get('text', '')})
            elif block.get('type') == 'tool_use':
                content.append({'type': 'tool_use', 'id': block['id'], 'name': block['name'], 'input': block.get('input', {})})
            # thinking blocks are omitted by default; other block types are ignored
        usage = response.get('usage', {})
        return {'content': content, 'stop_reason': response.get('stop_reason'), 'model': response.get('model', self.model),
                'response_id': response.get('id', ''),
                'usage': {'input_tokens': usage.get('input_tokens', 0), 'output_tokens': usage.get('output_tokens', 0),
                          'cache_read_input_tokens': usage.get('cache_read_input_tokens', 0) or 0}}


class OpenAIProvider(Provider):
    name = 'openai'

    def __init__(self, model=None, effort='medium', max_tokens=16000):
        self.model = model or os.environ.get('OPENAI_MODEL', OPENAI_DEFAULT_MODEL)
        self.effort = effort
        self.max_tokens = max_tokens

    def _headers(self):
        key = os.environ.get('OPENAI_API_KEY')
        if not key:
            raise ProviderError('Set OPENAI_API_KEY to use the OpenAI provider')
        return {'Authorization': 'Bearer ' + key}

    @staticmethod
    def _to_input(messages):
        items = []
        for message in messages:
            for block in message['content']:
                if block['type'] == 'text':
                    items.append({'role': message['role'], 'content': block['text']})
                elif block['type'] == 'tool_use':
                    items.append({'type': 'function_call', 'call_id': block['id'], 'name': block['name'],
                                  'arguments': json.dumps(block['input'])})
                elif block['type'] == 'tool_result':
                    items.append({'type': 'function_call_output', 'call_id': block['tool_use_id'], 'output': block['content']})
        return items

    def complete(self, system, messages, tools):
        body = {'model': self.model, 'store': False, 'max_output_tokens': self.max_tokens,
                'reasoning': {'effort': self.effort}, 'instructions': system,
                'input': self._to_input(messages),
                'tools': [{'type': 'function', 'name': t['name'], 'description': t['description'],
                           'parameters': _strict(t['input_schema']), 'strict': True} for t in tools]}
        response = _post('https://api.openai.com/v1/responses', self._headers(), body, self.timeout)
        if response.get('status') not in ('completed', 'incomplete'):
            raise ProviderError('Provider response did not complete')
        content, stop = [], 'end_turn'
        for item in response.get('output', []):
            kind = item.get('type')
            if kind == 'message':
                for part in item.get('content', []):
                    if part.get('type') == 'output_text':
                        content.append({'type': 'text', 'text': part.get('text', '')})
                    elif part.get('type') == 'refusal':
                        stop = 'refusal'
            elif kind == 'function_call':
                try:
                    arguments = loads(item.get('arguments', '{}'))
                except InputError:
                    arguments = {'__invalid_json__': item.get('arguments', '')}
                content.append({'type': 'tool_use', 'id': item['call_id'], 'name': item['name'], 'input': arguments})
                stop = 'tool_use'
        if response.get('status') == 'incomplete':
            stop = 'max_tokens'
        usage = response.get('usage', {})
        cached = (usage.get('input_tokens_details') or {}).get('cached_tokens', 0)
        return {'content': content, 'stop_reason': stop, 'model': response.get('model', self.model),
                'response_id': response.get('id', ''),
                'usage': {'input_tokens': usage.get('input_tokens', 0), 'output_tokens': usage.get('output_tokens', 0),
                          'cache_read_input_tokens': cached}}


class ReplayProvider(Provider):
    """Replays recorded completions in order. Used for examples, tests and CI.

    A recording is a list of completions as returned by a live provider. The
    replay checks that each recorded tool call names a tool that exists in the
    request, so a stale recording fails loudly instead of silently passing.
    """
    name = 'replay'

    def __init__(self, recording):
        if not isinstance(recording, list):
            raise InputError('Recording must be a list of completions')
        self.queue = list(recording)
        self.model = recording[0].get('model', 'recorded') if recording else 'recorded'

    def complete(self, system, messages, tools):
        if not self.queue:
            raise InputError('Replay has no recorded completion for this step')
        completion = self.queue.pop(0)
        names = {t['name'] for t in tools}
        for block in completion.get('content', []):
            if block.get('type') == 'tool_use' and block.get('name') not in names:
                raise InputError(f"Recorded call to unknown tool '{block.get('name')}'")
        return completion


class RecordingProvider(Provider):
    """Wraps a live provider and keeps every completion for later replay."""
    name = 'recording'

    def __init__(self, inner):
        self.inner = inner
        self.model = inner.model
        self.recording = []

    def complete(self, system, messages, tools):
        completion = self.inner.complete(system, messages, tools)
        self.recording.append(json.loads(json.dumps(completion)))
        return completion


def make_provider(name, model=None, effort='medium'):
    if name == 'anthropic':
        return AnthropicProvider(model, effort)
    if name == 'openai':
        return OpenAIProvider(model, effort)
    raise InputError("Provider must be 'anthropic' or 'openai'")


def default_provider_name():
    if os.environ.get('LLM_PROVIDER') in ('anthropic', 'openai'):
        return os.environ['LLM_PROVIDER']
    if os.environ.get('ANTHROPIC_API_KEY'):
        return 'anthropic'
    if os.environ.get('OPENAI_API_KEY'):
        return 'openai'
    return 'anthropic'


def timed(fn):
    start = time.monotonic()
    value = fn()
    return value, round((time.monotonic()-start)*1000)
