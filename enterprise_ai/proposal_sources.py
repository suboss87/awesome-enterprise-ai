"""Bounded, authenticated GitHub source snapshots for local proposal review."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from .common import InputError, obj, text, day, rows, unique, loads

MAX_RESPONSE = 200000
MAX_FILE = 40000
SHA = re.compile(r'[0-9a-f]{40}')


def digest(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise InputError('Expected a SHA-1 Git object identifier')
    return value


def path_parts(value):
    text(value, 'repository path', 512)
    parts = value.split('/')
    if len(parts) > 10 or any(not re.fullmatch(r'[A-Za-z0-9_.-]+', p) or p in ('.', '..') for p in parts):
        raise InputError('Source paths require 1-10 explicit safe path components')
    return parts


def validate_repository(repo):
    obj(repo, ['owner', 'repo', 'repository_id', 'branch'])
    for key in ('owner', 'repo'):
        value = text(repo[key], key, 100)
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value):
            raise InputError('Invalid repository name')
    if type(repo['repository_id']) is not int or repo['repository_id'] <= 0:
        raise InputError('Invalid repository ID')
    path_parts(repo['branch'])


def validate_manifest(manifest):
    obj(manifest, ['version', 'repositories', 'sources'])
    if type(manifest['version']) is not int or manifest['version'] != 1:
        raise InputError('Unsupported source manifest version')
    repositories = rows(manifest['repositories'], 'repositories', 5, 1)
    by_id = {}
    names = set()
    for repo in repositories:
        validate_repository(repo)
        name = (repo['owner'].lower(), repo['repo'].lower())
        if repo['repository_id'] in by_id or name in names:
            raise InputError('Duplicate repository')
        names.add(name); by_id[repo['repository_id']] = repo
    entries = rows(manifest['sources'], 'manifest sources', 20, 1)
    unique(entries)
    seen = set()
    for source in entries:
        obj(source, ['id', 'repository_id', 'path', 'approved_blob_sha', 'approval', 'valid_from', 'valid_until'])
        if type(source['repository_id']) is not int or source['repository_id'] not in by_id:
            raise InputError('Source repository is outside the allowlist')
        path_parts(source['path']); sha(source['approved_blob_sha'])
        binding = (source['repository_id'], source['path'])
        if binding in seen:
            raise InputError('Duplicate source path')
        seen.add(binding)
        if source['approval'] not in ('approved', 'draft', 'revoked', 'superseded'):
            raise InputError('Unknown source approval')
        if day(source['valid_from']) > day(source['valid_until']):
            raise InputError('Reversed source validity')
    return by_id


def validate_provenance(value):
    obj(value, ['provider', 'owner', 'repo', 'repository_id', 'branch', 'path', 'commit_sha', 'blob_sha', 'text_sha256', 'manifest_sha256'])
    if value['provider'] != 'github':
        raise InputError('Unknown source provider')
    validate_repository({k: value[k] for k in ('owner', 'repo', 'repository_id', 'branch')})
    path_parts(value['path']); sha(value['commit_sha']); sha(value['blob_sha'])
    for key in ('text_sha256', 'manifest_sha256'):
        if not isinstance(value[key], str) or not re.fullmatch(r'[0-9a-f]{64}', value[key]):
            raise InputError('Invalid provenance digest')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise InputError('GitHub redirect refused')


class GitHub:
    def __init__(self):
        try:
            result = subprocess.run(['gh', 'auth', 'token', '--hostname', 'github.com'],
                                    capture_output=True, text=True, timeout=10, check=True)
        except (OSError, subprocess.SubprocessError) as exc:
            raise InputError('GitHub authentication unavailable; sign in with gh') from exc
        self.token = result.stdout.strip()
        if not self.token or len(self.token) > 8192 or any(c.isspace() for c in self.token):
            raise InputError('Invalid GitHub credential')
        self.opener = urllib.request.build_opener(NoRedirect())
        self.deadline = time.monotonic() + 90

    def get(self, endpoint):
        if not endpoint.startswith('/repos/') or any(c in endpoint for c in ('\\', '\n', '\r')):
            raise InputError('Invalid GitHub API endpoint')
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise InputError('Source collection exceeded its time budget')
        request = urllib.request.Request('https://api.github.com' + endpoint, headers={
            'Authorization': 'Bearer ' + self.token,
            'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2026-03-10',
            'User-Agent': 'awesome-enterprise-ai-proposal-sources/1'})
        try:
            with self.opener.open(request, timeout=min(15, remaining)) as response:
                raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    raise InputError('GitHub response exceeds size limit')
                return loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise InputError('GitHub resource unavailable or unauthorized (404); deletion is not established') from None
            raise InputError(f'GitHub source refresh failed (HTTP {exc.code}); export withheld') from None
        except (OSError, urllib.error.URLError) as exc:
            raise InputError('GitHub source refresh unavailable; export withheld') from exc


def _collect(manifest, requirements, client=None):
    """Read each exact approved blob at a stable current branch; never fallback."""
    repos = validate_manifest(manifest)
    rows(requirements, 'requirements', 100, 1)
    for item in requirements:
        obj(item, ['id', 'text']); text(item['text'])
    unique(requirements)
    client = client or GitHub()
    heads = {}; prefixes = {}; roots = {}; trees = {}
    for rid, repo in repos.items():
        prefix = '/repos/' + repo['owner'] + '/' + repo['repo']
        metadata = client.get(prefix)
        if metadata.get('id') != rid or metadata.get('full_name', '').lower() != (repo['owner'] + '/' + repo['repo']).lower():
            raise InputError('Repository identity changed')
        ref = client.get(prefix + '/git/ref/heads/' + urllib.parse.quote(repo['branch'], safe='/'))
        if ref.get('object', {}).get('type') != 'commit':
            raise InputError('Expected a branch commit')
        head = sha(ref['object']['sha'])
        commit = client.get(prefix + '/git/commits/' + head)
        if commit.get('sha') != head:
            raise InputError('Commit identity mismatch')
        heads[rid] = head; prefixes[rid] = prefix; roots[rid] = sha(commit['tree']['sha'])
    sources = []
    for entry in manifest['sources']:
        rid = entry['repository_id']; repo = repos[rid]; prefix = prefixes[rid]
        tree_sha = roots[rid]; parts = path_parts(entry['path'])
        for index, component in enumerate(parts):
            key = (rid, tree_sha)
            if key not in trees:
                tree = client.get(prefix + '/git/trees/' + tree_sha)
                if tree.get('truncated') is not False or tree.get('sha') != tree_sha or not isinstance(tree.get('tree'), list):
                    raise InputError('Incomplete Git tree; source absence cannot be established')
                trees[key] = tree['tree']
            matches = [item for item in trees[key] if item.get('path') == component]
            if len(matches) != 1:
                raise InputError('Allowlisted source path absent or ambiguous at the pinned commit')
            item = matches[0]
            if index < len(parts) - 1:
                if item.get('type') != 'tree' or item.get('mode') != '040000':
                    raise InputError('Source path traverses a non-directory')
                tree_sha = sha(item['sha'])
            elif item.get('type') != 'blob' or item.get('mode') not in ('100644', '100755'):
                raise InputError('Source must be a regular file, not a symlink or submodule')
        blob_sha = sha(item['sha'])
        if blob_sha != entry['approved_blob_sha']:
            raise InputError('Source blob differs from the operator-approved manifest; review new content')
        if type(item.get('size')) is not int or not 0 < item['size'] <= MAX_FILE:
            raise InputError('Source file exceeds limits')
        content = client.get(prefix + '/contents/' + urllib.parse.quote(entry['path'], safe='/') + '?ref=' + heads[rid])
        if (content.get('type') != 'file' or content.get('path') != entry['path'] or
            content.get('sha') != blob_sha or content.get('encoding') != 'base64' or
            content.get('size') != item['size'] or content.get('submodule_git_url')):
            raise InputError('GitHub content metadata mismatch')
        encoded = content.get('content')
        if not isinstance(encoded, str) or len(encoded) > MAX_FILE * 2:
            raise InputError('Invalid encoded content size')
        try:
            raw = base64.b64decode(encoded.replace('\n', ''), validate=True)
            source_text = raw.decode('utf-8')
        except (ValueError, UnicodeError) as exc:
            raise InputError('Source must be valid base64 UTF-8 text') from exc
        if len(raw) != item['size'] or hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() != blob_sha:
            raise InputError('Source content integrity check failed')
        text(source_text, 'source text', 10000)
        proof = {'provider': 'github', **repo, 'path': entry['path'], 'commit_sha': heads[rid],
                 'blob_sha': blob_sha, 'text_sha256': hashlib.sha256(raw).hexdigest(), 'manifest_sha256': digest(manifest)}
        sources.append({'id': entry['id'], 'text': source_text, 'approval': entry['approval'],
                        'valid_from': entry['valid_from'], 'valid_until': entry['valid_until'], 'provenance': proof})
    for rid, repo in repos.items():
        current = client.get(prefixes[rid] + '/git/ref/heads/' + urllib.parse.quote(repo['branch'], safe='/'))
        if current.get('object', {}).get('sha') != heads[rid] or current.get('object', {}).get('type') != 'commit':
            raise InputError('Branch changed during source refresh; retry with a fresh review')
    packet = {'as_of': datetime.now(timezone.utc).date().isoformat(), 'requirements': requirements, 'sources': sources}
    if len((json.dumps(packet, ensure_ascii=False, indent=2) + '\n').encode()) > 500000:
        raise InputError('Source packet exceeds 500 KB')
    return packet


def _run_refresh(command, payload, timeout=100):
    """An enforceable wall-clock budget includes DNS, slow bodies and gh auth."""
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy(); env['PYTHONPATH'] = str(root)
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, cwd=root, env=env, start_new_session=True)
    deadline = time.monotonic() + timeout
    output = bytearray()
    pending = memoryview(payload)
    selector = None
    try:
        selector = selectors.DefaultSelector()
        os.set_blocking(process.stdin.fileno(), False)
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ)
        if pending:
            selector.register(process.stdin, selectors.EVENT_WRITE)
        else:
            process.stdin.close()
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            for key, _ in selector.select(remaining):
                if key.fileobj is process.stdin:
                    try:
                        count = os.write(process.stdin.fileno(), pending[:16384])
                        pending = pending[count:]
                    except BrokenPipeError:
                        pending = pending[:0]
                    if not pending:
                        selector.unregister(process.stdin)
                        process.stdin.close()
                else:
                    chunk = os.read(process.stdout.fileno(), min(65536, 1000001-len(output)))
                    output.extend(chunk)
                    if len(output) > 1000000:
                        raise InputError('Source worker response exceeds limit')
                    if not chunk:
                        selector.unregister(process.stdout)
                        process.stdout.close()
        process.wait(timeout=max(0, deadline-time.monotonic()))
        return process.returncode, bytes(output)
    except subprocess.TimeoutExpired:
        raise InputError('GitHub source refresh exceeded 100-second deadline; export withheld') from None
    finally:
        # Kill/reap the owned group without buffering any remaining output.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.stdin.close()
        process.stdout.close()
        process.wait()
        if selector is not None:
            selector.close()


def collect(manifest, requirements):
    validate_manifest(manifest)
    rows(requirements, 'requirements', 100, 1)
    for item in requirements:
        obj(item, ['id', 'text']); text(item['text'])
    unique(requirements)
    payload = json.dumps({'manifest': manifest, 'requirements': requirements}, allow_nan=False).encode()
    if len(payload) > 500000:
        raise InputError('Source request exceeds 500 KB')
    try:
        code, raw = _run_refresh([sys.executable, '-m', 'enterprise_ai.proposal_sources', '--worker'], payload)
        if len(raw) > 1000000:
            raise InputError('Source worker response exceeds limit')
        result = loads(raw)
        if code != 0 or not isinstance(result, dict) or 'packet' not in result:
            reason = result.get('error', 'Invalid source worker output') if isinstance(result, dict) else 'Invalid source worker output'
            raise InputError(reason)
        return result['packet']
    except (OSError, KeyError, TypeError, AttributeError) as exc:
        raise InputError('Source refresh unavailable or malformed; export withheld') from None


def worker():
    try:
        raw = sys.stdin.buffer.read(500001)
        if len(raw) > 500000:
            raise InputError('Source request exceeds 500 KB')
        request = loads(raw)
        obj(request, ['manifest', 'requirements'])
        packet = _collect(request['manifest'], request['requirements'])
        print(json.dumps({'packet': packet}, ensure_ascii=False))
        return 0
    except (InputError, OSError, ValueError, KeyError, TypeError, AttributeError):
        # Return only our own sanitized InputError messages, never API bodies or credentials.
        exc = sys.exc_info()[1]
        message = str(exc) if isinstance(exc, InputError) else 'Malformed or unavailable GitHub source'
        print(json.dumps({'error': message}))
        return 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--requirements', required=True, help='JSON object containing only requirements')
    args = parser.parse_args()
    from .proposal_review import read_file
    try:
        requirement_file = read_file(args.requirements)
        obj(requirement_file, ['requirements'])
        print(json.dumps(collect(read_file(args.manifest), requirement_file['requirements']), indent=2, ensure_ascii=False))
    except (InputError, OSError, KeyError, TypeError, ValueError) as exc:
        print('Source collection failed: ' + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(worker() if sys.argv[1:] == ['--worker'] else main())
