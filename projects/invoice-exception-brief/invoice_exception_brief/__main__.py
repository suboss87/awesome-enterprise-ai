import argparse
import json
import sys
from pathlib import Path
from .core import MAX_BYTES, InvalidEvidence, assess, load_bytes
from .render import render_html


def main():
    parser = argparse.ArgumentParser(description='Prepare a read-only invoice exception brief; never approves payment.')
    parser.add_argument('input', type=Path)
    parser.add_argument('--format', choices=['json', 'html'], default='json')
    args = parser.parse_args()
    try:
        with args.input.open('rb') as handle:
            data = load_bytes(handle.read(MAX_BYTES + 1))
        report = assess(data)
    except (InvalidEvidence, OSError, RecursionError) as exc:
        print('Invalid evidence: ' + str(exc), file=sys.stderr)
        return 2
    print(render_html(report) if args.format == 'html' else json.dumps(report, indent=2))
    return 1 if report['exceptions'] else 0


if __name__ == '__main__':
    sys.exit(main())
