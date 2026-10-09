"""Bounded local artifact import. No native row samples are carried into the packet."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]))
sys.path.insert(0,str(ROOT))
from enterprise_ai.common import InputError, loads, obj, rows
from workflow import import_gx, import_dbt


def read(path, maximum=2000000):
    with Path(path).open('rb') as stream: raw=stream.read(maximum+1)
    if len(raw)>maximum:raise InputError('Artifact exceeds byte limit')
    return loads(raw),hashlib.sha256(raw).hexdigest()


def collect(run_paths,suite_path,mapping_path,dbt_path,as_of,complete,max_age=72):
    rows(run_paths,'run paths',3,1)
    suite,_=read(suite_path);mapping,_=read(mapping_path);manifest,_=read(dbt_path)
    obj(mapping,['bindings'])
    bindings=rows(mapping['bindings'],'bindings',3,1)
    by_hash={}
    for binding in bindings:
        key=binding.get('artifact_sha256') if isinstance(binding,dict) else None
        if not isinstance(key,str) or key in by_hash:raise InputError('Conflicting artifact mappings')
        by_hash[key]=binding
    runs=[]
    for path in run_paths:
        artifact,sha=read(path)
        if sha not in by_hash:raise InputError('Artifact has no governed mapping')
        try:runs.append(import_gx(artifact,suite,by_hash[sha],sha))
        except (AttributeError,KeyError,TypeError) as exc:raise InputError('Malformed native GX artifact') from None
    try:lineage=import_dbt(manifest,complete)
    except (AttributeError,KeyError,TypeError) as exc:raise InputError('Malformed dbt manifest') from None
    packet={'schema_version':1,'exported_at':as_of,'as_of':as_of,'max_age_hours':max_age,
            'runs':runs,'lineage':lineage,'runbook_sources':[],'narrative_mode':'template'}
    if len(json.dumps(packet).encode())>500000:raise InputError('Normalized packet exceeds 500KB')
    return packet


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='append',required=True)
    for field in ('suite','mapping','dbt','output'):parser.add_argument('--'+field,required=True)
    parser.add_argument('--as-of',default=None,help='Explicit historical evaluation clock; default current UTC')
    parser.add_argument('--lineage-complete',action='store_true',help='Operator attests supplied declared graph coverage')
    parser.add_argument('--max-age-hours',type=int,default=72)
    args=parser.parse_args()
    try:
        packet=collect(args.run,args.suite,args.mapping,args.dbt,args.as_of or datetime.now(timezone.utc).isoformat(),args.lineage_complete,args.max_age_hours)
        Path(args.output).write_text(json.dumps(packet,indent=2)+'\n')
    except (InputError,OSError) as exc:parser.exit(2,str(exc)+'\n')
