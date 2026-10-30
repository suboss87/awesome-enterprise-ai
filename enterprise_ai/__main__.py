"""CLI: list, run, eval, serve."""
import argparse
import json
import sys
from pathlib import Path

from .catalog import catalog
from .common import InputError
from .llm import default_provider_name
from .runner import example_input, example_replay, execute


def main(argv=None):
    parser = argparse.ArgumentParser(prog='enterprise_ai', description='Enterprise AI agents with evals and approval gates')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('list', help='List the agents in the collection')

    run = sub.add_parser('run', help='Run one agent on one input')
    run.add_argument('project')
    run.add_argument('--input', type=Path, help='JSON input file (default: the project example)')
    run.add_argument('--provider', choices=['anthropic', 'openai', 'replay'], default=None,
                     help='Default: replay when no --input is given, else the provider whose key is set')
    run.add_argument('--model', help='Override the provider model id')
    run.add_argument('--effort', choices=['low', 'medium', 'high'], default='medium')
    run.add_argument('--replay', type=Path, help='Recorded completions to replay (default: the project example recording)')
    run.add_argument('--record', type=Path, help='Save the live completions to this file for later replay')
    run.add_argument('--trace', type=Path, help='Write the JSONL trace to this file')

    ev = sub.add_parser('eval', help='Run the labeled cases for one agent and write evals/REPORT.md')
    ev.add_argument('project')
    ev.add_argument('--provider', choices=['anthropic', 'openai'], default=None)
    ev.add_argument('--model')
    ev.add_argument('--effort', choices=['low', 'medium', 'high'], default='medium')
    ev.add_argument('--limit', type=int)
    ev.add_argument('--workers', type=int, default=4)
    ev.add_argument('--out', type=Path, help='Directory for raw results (default: evals/runs/<timestamp>)')
    ev.add_argument('--no-report', action='store_true', help='Do not overwrite evals/REPORT.md')
    ev.add_argument('--baseline-only', action='store_true', help='Score only the rules baseline; no model calls')

    serve = sub.add_parser('serve', help='Local browser workspace')
    serve.add_argument('--port', type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        if args.command == 'list':
            for spec in catalog():
                print(f"{spec['id']:32s} {spec['title']}  [{spec['category']}]")
            return 0
        if args.command == 'serve':
            from .server import serve as serve_http
            serve_http(args.port)
            return 0
        if args.command == 'run':
            data = json.loads(args.input.read_text()) if args.input else example_input(args.project)
            provider = args.provider or ('replay' if not args.input and not args.record else default_provider_name())
            replay = None
            if provider == 'replay':
                replay = json.loads(args.replay.read_text()) if args.replay else example_replay(args.project)
            output = execute(args.project, data, provider, replay=replay, record=bool(args.record), model=args.model, effort=args.effort)
            if args.record:
                args.record.write_text(json.dumps(output['execution'].pop('recording'), indent=1, ensure_ascii=False) + '\n')
                print(f'Recorded {args.record}', file=sys.stderr)
            if args.trace:
                args.trace.write_text(''.join(json.dumps(e) + '\n' for e in output['execution']['events']))
            print(json.dumps(output, indent=2, ensure_ascii=False))
            return 0
        if args.command == 'eval':
            from .evals import run_eval
            provider = args.provider or default_provider_name()
            summary, _rows = run_eval(args.project, provider, args.model, args.effort, args.limit, args.workers, args.out,
                                      not args.no_report and not args.baseline_only, with_agent=not args.baseline_only)
            print(json.dumps(summary, indent=2))
            return 0
    except InputError as exc:
        print(f'Failed: {exc}', file=sys.stderr)
        return 2  # an aborted eval writes no report
    except (OSError, json.JSONDecodeError) as exc:
        print(f'Failed to read input: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
