"""Run each project's isolated tests and honest offline demonstration."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from enterprise_ai.catalog import SLUGS


def main():
    subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=ROOT,check=True)
    for slug in SLUGS:
        print('\nVERIFY '+slug,flush=True)
        subprocess.run([sys.executable,'-m','unittest','discover','-s',f'projects/{slug}/tests','-v'],cwd=ROOT,check=True)
        run=subprocess.run([sys.executable,'-m','enterprise_ai','run',slug,'--input',f'projects/{slug}/examples/input.json',
            '--mode','replay','--responses',f'projects/{slug}/examples/responses.json'],cwd=ROOT,capture_output=True,text=True,check=True)
        result=json.loads(run.stdout)
        assert result['execution']['mode']=='replay'
        assert result['human_review_required'] is True
        print('Example replay verified: '+slug,flush=True)


if __name__=='__main__':main()
