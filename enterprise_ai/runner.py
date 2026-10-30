"""Run one agent once: live, replay or recording. Shared by CLI, web and evals."""
import hashlib
import json

from .agent import Trace
from .catalog import ROOT, load_agent
from .common import InputError
from .llm import RecordingProvider, ReplayProvider, make_provider

MAX_INPUT_BYTES = 1_000_000


def execute(slug, data, provider_name='anthropic', replay=None, record=False, model=None, effort='medium'):
    """Returns the project's output with an `execution` block attached.

    provider_name: 'anthropic' | 'openai' | 'replay'. For 'replay', `replay` is the
    recorded completion list. With record=True the live provider is wrapped and the
    recording is returned under execution.recording.
    """
    encoded = json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    if len(encoded) > MAX_INPUT_BYTES:
        raise InputError('Input exceeds 1 MB')
    if provider_name == 'replay':
        if replay is None:
            raise InputError('Replay requires a recording')
        provider = ReplayProvider(replay)
    else:
        provider = make_provider(provider_name, model, effort)
        if record:
            provider = RecordingProvider(provider)
    trace = Trace(slug, provider.name if not record else provider.inner.name)
    output = load_agent(slug).run(data, provider, trace)
    if provider_name == 'replay' and provider.queue:
        raise InputError('Replay contains unused completions; the recording is stale')
    output['human_review_required'] = True
    output['execution'] = {'mode': 'replay' if provider_name == 'replay' else 'live',
                           'input_sha256': hashlib.sha256(encoded).hexdigest(),
                           **trace.summary(), 'events': trace.events}
    if record:
        output['execution']['recording'] = provider.recording
    return output


def example_input(slug):
    path = ROOT/'projects'/slug/'examples/input.json'
    return json.loads(path.read_text())


def example_replay(slug):
    path = ROOT/'projects'/slug/'examples/replay.json'
    return json.loads(path.read_text())
