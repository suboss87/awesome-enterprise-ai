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
    artifacts=run.add_mutually_exclusive_group()
    artifacts.add_argument('--receipt',type=Path,help='Write a new private execution receipt, including failures')
    artifacts.add_argument('--run-dir',type=Path,help='Create a private new run directory for result and hash-bound receipt; no business output on stdout')
    run.add_argument('--deadline-seconds',type=float,default=120,help='Wall-clock worker deadline, at most 300 seconds')
    serve=sub.add_parser('serve');serve.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    try:
        if args.command=='list':
            print(json.dumps(catalog(),indent=2));return
        if args.command=='serve':
            from .server import serve
            serve(args.port);return
        from .execution import execute_bounded, write_receipt, write_run_artifacts, WorkflowFailure, start_receipt, finish_receipt
        if args.run_dir:
            args.run_dir.mkdir(mode=0o700)  # Fail before inference if the path exists.
            args.run_dir.chmod(0o700)
        receipt_path=args.run_dir/'receipt.json' if args.run_dir else args.receipt
        preflight=start_receipt(args.project,args.mode)
        started=time.monotonic()
        def read_bounded(path,limit):
            with path.open('rb') as stream:
                raw=stream.read(limit+1)
            if len(raw)>limit:
                raise InputError('Input file exceeds size limit')
            return loads(raw)
        output=None
        try:
            data=read_bounded(args.input,500000)
            responses=read_bounded(args.responses,5000000) if args.responses else None
            output=execute_bounded(args.project,data,args.mode,responses,deadline_seconds=args.deadline_seconds)
            if args.run_dir:
                write_run_artifacts(args.run_dir,output)
        except (InputError,OSError,UnicodeError,RecursionError,ValueError,TypeError) as exc:
            receipt=exc.receipt if isinstance(exc,WorkflowFailure) else finish_receipt(
                dict(output['execution']['receipt']) if output else preflight,started,'failed',
                'artifact_publication_failed' if output else 'input_rejected')
            if receipt_path:
                write_receipt(receipt_path,receipt)
            raise InputError(str(exc) if isinstance(exc,WorkflowFailure) else 'Input could not be read or validated; no result produced') from None
        if args.run_dir:
            print(json.dumps({'status':'succeeded','run_id':output['execution']['receipt']['run_id']}))
        else:
            if args.receipt:
                write_receipt(args.receipt,output['execution']['receipt'])
            print(json.dumps(output,indent=2,ensure_ascii=False))
    except (InputError,OSError,UnicodeError,RecursionError) as exc:
        print('Workflow failed: '+str(exc),file=sys.stderr);sys.exit(2)


if __name__=='__main__':
    main()
