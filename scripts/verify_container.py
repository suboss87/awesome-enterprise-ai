"""Exercise actual isolated container jobs; no provider key or network required."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from enterprise_ai.catalog import SLUGS


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--image',default='enterprise-ai:ci')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='enterprise-ai-container-') as temporary:
        runs=Path(temporary)/'runs';runs.mkdir(mode=0o700)
        command=['docker','run','--rm','--network=none','--read-only',
            '--cap-drop=ALL','--security-opt=no-new-privileges:true',
            '--pids-limit=64','--memory=256m','--cpus=1',
            '--user',f'{os.getuid()}:{os.getgid()}',
            '--mount',f'type=bind,src={runs},dst=/runs',
            '--mount',f'type=bind,src={ROOT / "projects"},dst=/fixtures,readonly',args.image]
        for slug in SLUGS:
            job=['run',slug,'--input',f'/fixtures/{slug}/examples/input.json',
                '--mode','replay','--responses',f'/fixtures/{slug}/examples/responses.json',
                '--run-dir',f'/runs/{slug}']
            run=subprocess.run(command+job,capture_output=True,text=True,timeout=180,check=True)
            log=json.loads(run.stdout)
            if set(log)!={'status','run_id'} or log['status']!='succeeded' or run.stderr:
                raise RuntimeError('Unexpected container job log')
            directory=runs/slug;raw=(directory/'result.json').read_bytes()
            receipt=json.loads((directory/'receipt.json').read_text());result=json.loads(raw)
            if receipt['result_sha256']!=hashlib.sha256(raw).hexdigest() or receipt['result_bytes']!=len(raw):
                raise RuntimeError('Result/receipt binding differs')
            if receipt['run_id']!=log['run_id'] or not result['human_review_required']:
                raise RuntimeError('Run identity or human-review boundary differs')
            for path,mode in [(directory,0o700),(directory/'result.json',0o600),(directory/'receipt.json',0o600)]:
                if path.stat().st_mode&0o777!=mode:raise RuntimeError('Artifact permissions differ')
            # Reusing a completed path must fail and preserve the previous result.
            rejected=subprocess.run(command+job,capture_output=True,text=True,timeout=30)
            if rejected.returncode!=2 or rejected.stdout or raw!=(directory/'result.json').read_bytes():
                raise RuntimeError('Existing result was overwritten or falsely reported')
            print('Isolated container replay verified: '+slug,flush=True)
        # Actually exercise read-only/non-root/no-new-privilege controls, not just Docker flags.
        probe_code="""import os,pathlib
assert os.getuid()!=0
assert not list(pathlib.Path('/app').rglob('*.json'))
assert not list(pathlib.Path('/app/projects').rglob('examples'))
assert os.statvfs('/app').f_flag & os.ST_RDONLY
lines=pathlib.Path('/proc/self/status').read_text().splitlines()
assert any(line.split()==['NoNewPrivs:','1'] for line in lines)
assert int(next(line.split()[1] for line in lines if line.startswith('CapEff:')),16)==0
try:
    pathlib.Path('/app/forbidden-write').write_text('no')
except OSError:
    pass
else:
    raise RuntimeError('Writable application filesystem')
"""
        probe=command[:-1]+['--entrypoint','python3',args.image,'-c',probe_code]
        subprocess.run(probe,capture_output=True,text=True,timeout=30,check=True)
        # A failed job gets a failure receipt and no business result.
        failure=subprocess.run(command+['run','customer-resolution','--input','/missing',
            '--mode','replay','--run-dir','/runs/rejected'],capture_output=True,text=True,timeout=30)
        directory=runs/'rejected'
        if failure.returncode!=2 or failure.stdout or (directory/'result.json').exists() or json.loads((directory/'receipt.json').read_text())['status']!='failed':
            raise RuntimeError('Failed container job published a result')
        print('Container privilege, failure and preservation checks passed.',flush=True)


if __name__=='__main__':main()
