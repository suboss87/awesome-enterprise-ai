"""Explicit allowlist of agents. No user-controlled import paths."""
import importlib.util
from pathlib import Path

from .common import InputError

ROOT = Path(__file__).resolve().parents[1]
SLUGS = ('ap-exception-agent', 'support-resolution-agent', 'incident-investigation-agent',
         'claims-intake-agent', 'vulnerability-triage-agent')


def _module(slug, name):
    if slug not in SLUGS:
        raise InputError('Unknown project')
    path = ROOT/'projects'/slug/name
    if not path.is_file():
        raise InputError(f'{slug}/{name} is not available')
    spec = importlib.util.spec_from_file_location(f"enterprise_ai_projects.{slug.replace('-', '_')}.{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_agent(slug):
    return _module(slug, 'agent.py')


def load_baseline(slug):
    return _module(slug, 'baseline.py')


def load_scorer(slug):
    return _module(slug, 'evals/score.py')


def available():
    return [s for s in SLUGS if (ROOT/'projects'/s/'agent.py').is_file()]


def catalog():
    return [load_agent(s).SPEC for s in available()]
