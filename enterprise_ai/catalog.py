"""Explicit project allowlist. No user-controlled import paths."""
import importlib.util
from pathlib import Path
from .common import InputError

ROOT=Path(__file__).resolve().parents[1]
SLUGS=('customer-resolution','incident-operations','exposure-review','business-insights',
       'inventory-decisions','asset-operations','claims-intake','proposal-operations',
       'account-intelligence','workforce-onboarding')


def load(slug):
    if slug not in SLUGS:
        raise InputError('Unknown project')
    path=ROOT/'projects'/slug/'workflow.py'
    if not path.is_file():
        raise InputError('Project implementation is not available yet')
    spec=importlib.util.spec_from_file_location('enterprise_project_'+slug.replace('-','_'),path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def catalog():
    return [load(slug).SPEC for slug in SLUGS if (ROOT/'projects'/slug/'workflow.py').exists()]
