"""Bounded child execution and content-free operational receipts.

Receipts describe local execution; they are not signed audit records. Business
records stay in the returned work product, never in the failure receipt.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

from .catalog import ROOT, SLUGS
from .common import InputError, loads

DEFAULT_DEADLINE_SECONDS = 120
MAX_WIRE_BYTES = 5_000_000
MAX_RESULT_FILE_BYTES = 10_000_000


class WorkflowFailure(InputError):
    def __init__(self, message, receipt):
        super().__init__(message)
        self.receipt = receipt


def start_receipt(slug, mode):
    files = ['common.py', 'provider.py', 'catalog.py', '__main__.py', 'execution.py', 'worker.py']
    hashes = {f'enterprise_ai/{name}': hashlib.sha256((ROOT/'enterprise_ai'/name).read_bytes()).hexdigest()
              for name in files}
    if slug in SLUGS:
        name = f'projects/{slug}/workflow.py'
        hashes[name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    return {'receipt_version': 1, 'run_id': str(uuid.uuid4()),
            'project': slug if slug in SLUGS else 'unknown',
            'mode': mode if mode in ('live', 'replay') else 'invalid',
            'started_at': datetime.now(timezone.utc).isoformat(),
            'status': 'running', 'source_sha256': hashes}


def finish_receipt(receipt, started, status, category=None):
    receipt.update(status=status, elapsed_seconds=round(time.monotonic()-started, 6),
                   finished_at=datetime.now(timezone.utc).isoformat())
    if category:
        receipt['failure_category'] = category
    return receipt


def _run_process(command, payload, timeout):
    """subprocess.run kills and reaps this child when its wall-clock wait expires."""
    env = os.environ.copy()
    env['PYTHONPATH'] = str(ROOT)
    return subprocess.run(command, input=payload, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, cwd=ROOT, env=env,
                          timeout=timeout, check=False)


def execute_bounded(slug, data, mode='live', responses=None, *, deadline_seconds=DEFAULT_DEADLINE_SECONDS):
    """CLI/web boundary. Use execute directly only inside a managed worker."""
    if isinstance(deadline_seconds, bool) or not isinstance(deadline_seconds, (int, float)) or not math.isfinite(deadline_seconds) or not 0 < deadline_seconds <= 300:
        raise InputError('Deadline must be greater than zero and at most 300 seconds')
    receipt = start_receipt(slug, mode)
    started = time.monotonic()
    receipt['deadline_seconds'] = deadline_seconds
    try:
        if mode not in ('live', 'replay'):
            raise InputError('Unknown execution mode')
        if mode == 'live' and responses is not None:
            raise InputError('Recorded responses require replay mode')
        payload = json.dumps({'project': slug, 'data': data, 'mode': mode, 'responses': responses}, allow_nan=False).encode()
        if len(payload) > MAX_WIRE_BYTES:
            raise InputError('Worker request exceeds size limit')
        process = _run_process([sys.executable, '-m', 'enterprise_ai.worker'], payload, deadline_seconds)
        if len(process.stdout) > MAX_WIRE_BYTES:
            raise InputError('Worker response exceeds size limit')
        envelope = loads(process.stdout)
        if not isinstance(envelope, dict) or process.returncode not in (0, 2):
            raise ValueError('Invalid worker response')
        if process.returncode != 0 or envelope.get('status') != 'succeeded':
            finish_receipt(receipt, started, 'failed', 'workflow_rejected')
            raise WorkflowFailure('Workflow rejected input or provider output; no result produced', receipt)
        output = envelope['output']
        if not isinstance(output, dict) or output.get('execution', {}).get('mode') != mode:
            raise ValueError('Invalid worker output')
        finish_receipt(receipt, started, 'succeeded')
        receipt['input_sha256'] = output['execution']['input_sha256']
        receipt['calls'] = [{key: call[key] for key in ('mode','model','response_id','prompt_sha256','schema_sha256') if key in call}
                            for call in output['execution'].get('calls',[])]
        output['execution']['receipt'] = receipt
        if len(json.dumps(output,indent=2,ensure_ascii=False,allow_nan=False).encode())+1 > MAX_RESULT_FILE_BYTES:
            raise InputError('Serialized result exceeds file size limit')
        return output
    except WorkflowFailure:
        raise
    except subprocess.TimeoutExpired:
        finish_receipt(receipt, started, 'failed', 'deadline_exceeded')
        raise WorkflowFailure('Workflow deadline exceeded; worker terminated, no result produced', receipt) from None
    except (InputError, ValueError, TypeError, RecursionError, KeyError, OSError):
        finish_receipt(receipt, started, 'failed', 'execution_error')
        raise WorkflowFailure('Invalid input or unavailable worker; no result produced', receipt) from None


def write_receipt(path, receipt):
    """Opt-in private new file, never overwrite an existing receipt or symlink."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(Path(path), flags, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write('\n')
