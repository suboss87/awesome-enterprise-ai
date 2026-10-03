"""Local snapshot assessment; template mode never calls a provider."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]));sys.path.insert(0,str(ROOT))
from enterprise_ai.common import InputError, ReplayAI
from enterprise_ai.execution import execute_bounded
from import_native import read
from workflow import run

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True)
    parser.add_argument('--mode',choices=('template','replay','live'),default='template')
    parser.add_argument('--responses')
    args=parser.parse_args()
    try:
        packet,_=read(args.input,500000)
        packet['narrative_mode']='template' if args.mode=='template' else 'ai'
        if args.responses and args.mode!='replay':
            raise InputError('Recorded responses require replay mode')
        if args.mode=='template':
            output=run(packet,ReplayAI([]))
        else:
            responses=read(args.responses)[0] if args.mode=='replay' and args.responses else None
            output=execute_bounded('data-repair-evidence',packet,args.mode,responses)
        print(json.dumps(output,indent=2))
    except (InputError,OSError) as exc:parser.exit(2,str(exc)+'\n')
