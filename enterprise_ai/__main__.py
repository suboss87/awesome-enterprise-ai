import argparse
import hashlib
import json
import sys
from pathlib import Path
from .catalog import catalog, load
from .common import InputError, ReplayAI, loads
from .provider import LiveAI


def execute(slug,data,mode='live',responses=None):
    encoded=json.dumps(data,ensure_ascii=False,sort_keys=True).encode()
    if len(encoded)>500000:
        raise InputError('Input exceeds 500 KB')
    ai=LiveAI() if mode=='live' else ReplayAI(responses or [])
    output=load(slug).run(data,ai)
    if mode=='replay' and ai.responses:
        raise InputError('Replay contains unused responses')
    output['execution']={'mode':mode,'calls':ai.calls,'input_sha256':hashlib.sha256(encoded).hexdigest()}
    return output


def main():
    parser=argparse.ArgumentParser(description='Enterprise AI workflows')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('list')
    run=sub.add_parser('run');run.add_argument('project');run.add_argument('--input',required=True,type=Path)
    run.add_argument('--mode',choices=['live','replay'],default='live')
    run.add_argument('--responses',type=Path,help='Explicit recorded model responses for offline demonstration')
    serve=sub.add_parser('serve');serve.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    try:
        if args.command=='list':
            print(json.dumps(catalog(),indent=2));return
        if args.command=='serve':
            from .server import serve
            serve(args.port);return
        raw=args.input.read_bytes()
        if len(raw)>500000:
            raise InputError('Input exceeds 500 KB')
        data=loads(raw)
        responses=loads(args.responses.read_bytes()) if args.responses else None
        if args.mode=='live' and responses is not None:
            raise InputError('Recorded responses require replay mode')
        print(json.dumps(execute(args.project,data,args.mode,responses),indent=2,ensure_ascii=False))
    except (InputError,OSError,UnicodeError,RecursionError) as exc:
        print('Workflow failed: '+str(exc),file=sys.stderr);sys.exit(2)


if __name__=='__main__':
    main()
