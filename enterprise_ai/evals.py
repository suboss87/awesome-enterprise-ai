"""Evaluation runner: agent and baseline on labeled cases, one committed report.

A case line in evals/cases.jsonl:
  {"id": "...", "category": "...", "input": {...}, "expected": {...}}
A project's evals/score.py exposes:
  METRICS = [{"name": ..., "label": ..., "kind": "rate"|"mean"|"zero"}]
  score(case, output) -> {metric_name: bool|number|None}
    kind "rate": share of True; "mean": average; "zero": a count that must stay 0.
"""
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from .catalog import ROOT, load_baseline, load_scorer
from .common import InputError
from .runner import execute


class EvalAborted(InputError):
    """The run stopped early because the provider account rejected calls (credits, key). Nothing is reported."""


def _is_account_failure(exc):
    text = str(exc)
    return any(marker in text for marker in ('HTTP 401', 'HTTP 402', 'HTTP 403', 'no credits', 'insufficient_quota', 'billing', 'Set ANTHROPIC_API_KEY', 'Set OPENAI_API_KEY'))


def load_cases(slug, limit=None):
    path = ROOT/'projects'/slug/'evals/cases.jsonl'
    cases = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    ids = [c['id'] for c in cases]
    if len(set(ids)) != len(ids):
        raise InputError('Duplicate case ids')
    return cases[:limit] if limit else cases


def _run_case(slug, case, provider, model, effort, scorer, baseline, with_agent=True):
    row = {'id': case['id'], 'category': case.get('category', 'uncategorized')}
    started = time.monotonic()
    if not with_agent:
        row['agent'] = None
    try:
        if not with_agent:
            raise InputError('agent skipped')
        output = execute(slug, case['input'], provider, model=model, effort=effort)
        row['agent'] = scorer.score(case, output)
        row['agent_cost_usd'] = output['execution'].get('cost_usd')
        row['agent_model'] = output['execution'].get('model')
        row['agent_latency_ms'] = output['execution'].get('latency_ms')
        row['agent_summary'] = output.get('summary')
        row['agent_route'] = output.get('metrics', {}).get('route')
    except InputError as exc:
        if _is_account_failure(exc):
            raise EvalAborted(f'Provider account problem on case {case["id"]}: {exc}') from exc
        row['agent'] = scorer.score(case, None)
        row['agent_error'] = str(exc)
        row['agent_latency_ms'] = round((time.monotonic()-started)*1000)
        if not with_agent:
            row['agent'] = None
            del row['agent_error']
    try:
        base_out = baseline.run(case['input'])
        row['baseline'] = scorer.score(case, base_out)
        row['baseline_route'] = base_out.get('metrics', {}).get('route')
    except InputError as exc:
        row['baseline'] = scorer.score(case, None)
        row['baseline_error'] = str(exc)
    return row


def aggregate(rows, metrics, key):
    out = {}
    for metric in metrics:
        values = [r[key].get(metric['name']) for r in rows if r.get(key) is not None]
        values = [v for v in values if v is not None]
        if not values:
            out[metric['name']] = None
        elif metric['kind'] == 'rate':
            out[metric['name']] = round(100*sum(1 for v in values if v)/len(values), 1)
        elif metric['kind'] == 'zero':
            out[metric['name']] = sum(1 for v in values if v)
        else:
            out[metric['name']] = round(statistics.fmean(values), 3)
    return out


def _fmt(metric, value):
    if value is None:
        return 'n/a'
    if metric['kind'] == 'rate':
        return f'{value}%'
    return str(value)


def _percentile(values, pct):
    if not values:
        return None
    values = sorted(values)
    index = min(len(values)-1, max(0, round(pct/100*(len(values)-1))))
    return values[index]


def run_eval(slug, provider='anthropic', model=None, effort='medium', limit=None, workers=4, out_dir=None, write_report=True, with_agent=True):
    scorer = load_scorer(slug)
    baseline = load_baseline(slug)
    cases = load_cases(slug, limit)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
        rows = list(pool.map(lambda c: _run_case(slug, c, provider, model, effort, scorer, baseline, with_agent), cases))
    metrics = scorer.METRICS
    summary = {'project': slug, 'date': date.today().isoformat(), 'provider': provider,
               'model': model or _model_used(rows, slug), 'effort': effort, 'n': len(rows),
               'agent': aggregate(rows, metrics, 'agent'), 'baseline': aggregate(rows, metrics, 'baseline'),
               'agent_errors': sum(1 for r in rows if 'agent_error' in r), 'with_agent': with_agent,
               'cost_usd_total': _sum([r.get('agent_cost_usd') for r in rows]),
               'cost_usd_per_case': _mean([r.get('agent_cost_usd') for r in rows]),
               'latency_ms_p50': _percentile([r['agent_latency_ms'] for r in rows if r.get('agent_latency_ms')], 50),
               'latency_ms_p95': _percentile([r['agent_latency_ms'] for r in rows if r.get('agent_latency_ms')], 95)}
    out_dir = Path(out_dir) if out_dir else ROOT/'projects'/slug/'evals/runs'/time.strftime('%Y%m%d-%H%M%S')
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir/'results.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rows))
    (out_dir/'summary.json').write_text(json.dumps(summary, indent=2))
    if write_report:
        (ROOT/'projects'/slug/'evals/REPORT.md').write_text(render_report(summary, rows, metrics, scorer))
    return summary, rows


def _mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values)/len(values), 4) if values else None


def _sum(values):
    values = [v for v in values if v is not None]
    return round(sum(values), 4) if values else None


def _model_used(rows, slug):
    models = [r.get('agent_model') for r in rows if r.get('agent_model')]
    return max(set(models), key=models.count) if models else None


def render_report(summary, rows, metrics, scorer):
    lines = [f"# Evaluation report: {summary['project']}", '',
             f"Run on {summary['date']} with provider `{summary['provider']}`, model `{summary.get('model') or 'see results'}`, "
             f"effort `{summary['effort']}`, {summary['n']} labeled synthetic cases. "
             f"Agent errors: {summary['agent_errors']}. Total model cost: "
             f"{'USD '+str(summary['cost_usd_total'])+' (USD '+str(summary.get('cost_usd_per_case'))+' per case)' if summary['cost_usd_total'] is not None else 'not priced'}. "
             f"Latency p50 {summary['latency_ms_p50']} ms, p95 {summary['latency_ms_p95']} ms.", '',
             'All cases are fictional and generated by `evals/generate_cases.py`. Labels were fixed before any model call. '
             'The baseline runs the same deterministic rules without a model.', '',
             '## Results', '', '| Metric | Agent | Baseline |', '|---|---:|---:|']
    for metric in metrics:
        lines.append(f"| {metric['label']} | {_fmt(metric, summary['agent'].get(metric['name']))} | {_fmt(metric, summary['baseline'].get(metric['name']))} |")
    primary = getattr(scorer, 'PRIMARY', metrics[0]['name'])
    cats = sorted({r['category'] for r in rows})
    lines += ['', f"## By category ({next(m['label'] for m in metrics if m['name']==primary)})", '',
              '| Category | Cases | Agent | Baseline |', '|---|---:|---:|---:|']
    for cat in cats:
        sub = [r for r in rows if r['category'] == cat]
        a = aggregate(sub, [m for m in metrics if m['name'] == primary], 'agent')[primary]
        b = aggregate(sub, [m for m in metrics if m['name'] == primary], 'baseline')[primary]
        pm = next(m for m in metrics if m['name'] == primary)
        lines.append(f'| {cat} | {len(sub)} | {_fmt(pm, a)} | {_fmt(pm, b)} |')
    failures = [r for r in rows if r.get('agent') and not r['agent'].get(primary)]
    lines += ['', '## Agent failures', '']
    if not failures:
        lines.append('No agent failure on the primary metric in this run.')
    else:
        lines += ['| Case | Category | Failed checks | Note |', '|---|---|---|---|']
        for r in failures[:12]:
            failed = [m['label'] for m in metrics if m['kind'] == 'rate' and r['agent'].get(m['name']) is False] + \
                     [m['label'] for m in metrics if m['kind'] == 'zero' and r['agent'].get(m['name'])]
            note = r.get('agent_error') or (f"route {r.get('agent_route')}" if r.get('agent_route') else '')
            lines.append(f"| {r['id']} | {r['category']} | {', '.join(failed) or primary} | {note} |")
        if len(failures) > 12:
            lines.append(f'| … | | {len(failures)-12} more in results.jsonl | |')
    lines += ['', '## How to reproduce', '', '```sh',
              f"python3 -m enterprise_ai eval {summary['project']} --provider {summary['provider']}" + (f" --model {summary['model']}" if summary.get('model') else ''),
              '```', '', 'Raw per-case results stay in `evals/runs/` (gitignored). Synthetic results do not establish production accuracy; '
              'run the same harness on your own labeled cases before adoption.']
    return '\n'.join(lines) + '\n'
