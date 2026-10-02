import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from .catalog import catalog, load
from .common import InputError, ReplayAI, loads
from .provider import LiveAI


def execute(slug,data,mode='live',responses=None):
    if mode not in ('live','replay'):
        raise InputError('Unknown execution mode')
    if mode=='live' and responses is not None:
        raise InputError('Recorded responses require replay mode')
    encoded=json.dumps(data,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()
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
    run.add_argument('--receipt',type=Path,help='Write a new private execution receipt, including failures')
    run.add_argument('--deadline-seconds',type=float,default=120,help='Wall-clock worker deadline, at most 300 seconds')
    serve=sub.add_parser('serve');serve.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    try:
        if args.command=='list':
            print(json.dumps(catalog(),indent=2));return
        if args.command=='serve':
            from .server import serve
            serve(args.port);return
        from .execution import execute_bounded, write_receipt, WorkflowFailure, start_receipt, finish_receipt
        preflight=start_receipt(args.project,args.mode)
        started=time.monotonic()
        def read_bounded(path,limit):
            with path.open('rb') as stream:
                raw=stream.read(limit+1)
            if len(raw)>limit:
                raise InputError('Input file exceeds size limit')
            return loads(raw)
        try:
            data=read_bounded(args.input,500000)
            responses=read_bounded(args.responses,5000000) if args.responses else None
            output=execute_bounded(args.project,data,args.mode,responses,deadline_seconds=args.deadline_seconds)
        except (InputError,OSError,UnicodeError,RecursionError,ValueError,TypeError) as exc:
            receipt=exc.receipt if isinstance(exc,WorkflowFailure) else finish_receipt(preflight,started,'failed','input_rejected')
            if args.receipt:
                write_receipt(args.receipt,receipt)
            raise InputError(str(exc) if isinstance(exc,WorkflowFailure) else 'Input could not be read or validated; no result produced') from None
        if args.receipt:
            write_receipt(args.receipt,output['execution']['receipt'])
        print(json.dumps(output,indent=2,ensure_ascii=False))
    except (InputError,OSError,UnicodeError,RecursionError) as exc:
        print('Workflow failed: '+str(exc),file=sys.stderr);sys.exit(2)


if __name__=='__main__':
    main()
