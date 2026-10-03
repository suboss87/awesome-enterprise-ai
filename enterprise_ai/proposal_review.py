"""Local, OS-account-bound review ledger with authenticated GitHub source refresh."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pwd
import sqlite3
import stat
import sys
from . import proposal_sources

from .catalog import load
from .execution import MAX_RESULT_FILE_BYTES
from .common import InputError, ReplayAI, day, loads, text, unique


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def today():
    return datetime.now(timezone.utc).date()


def packet_binding(packet):
    # Every source is bound: new/changed contradictory evidence must trigger review too.
    return digest({k: v for k, v in packet.items() if k != 'as_of'})


def validate(packet, output):
    if not isinstance(output, dict) or output.get('project') != 'proposal-operations':
        raise InputError('Expected proposal-operations result')
    matrix = output.get('matrix')
    if not isinstance(matrix, list):
        raise InputError('Missing matrix')
    unique(matrix, 'requirement_id')
    answers = []
    for row in matrix:
        status = row.get('status')
        if status not in ('supported', 'gap', 'conflict', 'evidence_review'):
            raise InputError('Invalid answer status')
        answers.append({'requirement_id': row['requirement_id'],
                        'status': 'supported' if status == 'evidence_review' else status,
                        'draft': 'Withheld pending evidence review.' if status == 'evidence_review' else row.get('draft'),
                        'evidence': row.get('evidence')})
    checked = load('proposal-operations').run(packet, ReplayAI([{'answers': answers}]))
    originals = {row['requirement_id']: row for row in matrix}
    for row in checked['matrix']:
        original = originals[row['requirement_id']]
        if original.get('requirement') != row['requirement']:
            raise InputError('Requirement binding mismatch')
        for key in ('status', 'draft', 'evidence', 'invalid_sources'):
            if original.get(key) != row[key]:
                raise InputError('Draft or source eligibility mismatch')
    return matrix


def policy_file(path):
    """Read the same operator policy at each decision, never an embedded old copy."""
    path = Path(path).absolute()
    parent = path.parent.stat()
    if parent.st_uid != os.getuid() or parent.st_mode & 0o077:
        raise InputError('Source manifest directory must be private and owned by this OS account')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise InputError('Source manifest must be an owned regular file without group/other write access')
        raw = handle.read(500001)
        if len(raw) > 500000:
            raise InputError('Source manifest exceeds 500 KB')
    return path.resolve(), loads(raw)


def check_policy_binding(packet, manifest):
    expected = proposal_sources.digest(manifest)
    if any(source.get('provenance', {}).get('manifest_sha256') != expected for source in packet['sources']):
        raise InputError('Operator source policy changed; generate and review a new draft before accessing sources')


class Ledger:
    def __init__(self, path):
        path = Path(path)
        parent = path.parent.stat()
        if parent.st_uid != os.getuid() or parent.st_mode & 0o077:
            raise InputError('Ledger directory must be private (0700) and owned by this OS account')
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise InputError('Ledger must be a private regular file owned by this OS account')
        finally:
            os.close(fd)
        self.db = sqlite3.connect(path, timeout=10, isolation_level=None)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS drafts (
              id TEXT PRIMARY KEY, packet TEXT NOT NULL, output TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS source_policies (
              draft_id TEXT PRIMARY KEY REFERENCES drafts(id), manifest_path TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS decisions (
              sequence INTEGER PRIMARY KEY AUTOINCREMENT,
              draft_id TEXT NOT NULL REFERENCES drafts(id), requirement_id TEXT NOT NULL,
              decision TEXT NOT NULL CHECK(decision IN ('approve','reject')),
              reviewer_uid INTEGER NOT NULL, reviewer_name TEXT NOT NULL,
              recorded_at TEXT NOT NULL, note TEXT NOT NULL);
        ''')

    def close(self):
        self.db.close()

    def stage(self, packet, output, source_manifest=None):
        validate(packet, output)
        bound = any('provenance' in source for source in packet['sources'])
        policy_path = None
        if bound:
            if source_manifest is None:
                raise InputError('GitHub-bound drafts require an operator source manifest file')
            policy_path, manifest = policy_file(source_manifest)
            check_policy_binding(packet, manifest)
            fresh = proposal_sources.collect(manifest, packet['requirements'])
            _, refreshed_policy = policy_file(policy_path)
            check_policy_binding(packet, refreshed_policy)
            if packet_binding(packet) != packet_binding(fresh):
                raise InputError('GitHub source packet changed before staging')
        elif source_manifest is not None:
            raise InputError('Source manifest requires a GitHub-bound packet')
        identity = digest({'packet': packet, 'output': output})
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.db.execute('INSERT OR IGNORE INTO drafts VALUES (?,?,?)',
                            (identity, canonical(packet), canonical(output)))
            if policy_path:
                previous = self.db.execute('SELECT manifest_path FROM source_policies WHERE draft_id=?', (identity,)).fetchone()
                if previous and previous[0] != str(policy_path):
                    raise InputError('Cannot replace the staged operator policy path')
                self.db.execute('INSERT OR IGNORE INTO source_policies VALUES (?,?)', (identity, str(policy_path)))
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise
        return identity

    def read(self, identity):
        row = self.db.execute('SELECT packet,output FROM drafts WHERE id=?', (identity,)).fetchone()
        if row is None:
            raise InputError('Unknown draft')
        packet, output = map(loads, row)
        if digest({'packet': packet, 'output': output}) != identity:
            raise InputError('Stored draft integrity check failed')
        validate(packet, output)
        return packet, output

    def current_rows(self, identity, current):
        packet, output = self.read(identity)
        if any('provenance' in source for source in packet['sources']):
            if current is not None:
                raise InputError('Manual current input cannot replace authenticated GitHub refresh')
            policy = self.db.execute('SELECT manifest_path FROM source_policies WHERE draft_id=?', (identity,)).fetchone()
            if not policy:
                raise InputError('GitHub draft has no bound operator policy; stage again')
            _, manifest = policy_file(policy[0])
            check_policy_binding(packet, manifest)
            current = proposal_sources.collect(manifest, packet['requirements'])
            _, refreshed_policy = policy_file(policy[0])
            check_policy_binding(packet, refreshed_policy)
        if not isinstance(current, dict):
            raise InputError('Manual drafts require current input')
        if day(current.get('as_of')) != today():
            raise InputError('Current input as_of must be today in UTC')
        if packet_binding(packet) != packet_binding(current):
            raise InputError('Requirements or source snapshot changed; generate and review a new draft')
        # Re-evaluate actual validity today, never the historical generation date.
        validate(current, output)
        return {row['requirement_id']: row for row in output['matrix']}, current

    def latest(self, identity, requirement):
        return self.db.execute('''SELECT sequence,decision,reviewer_uid,reviewer_name,recorded_at,note
            FROM decisions WHERE draft_id=? AND requirement_id=? ORDER BY sequence DESC LIMIT 1''',
            (identity, requirement)).fetchone()

    def recheck_policy(self, identity, current):
        """Check local immutable state/policy after lock acquisition, without network."""
        packet, output = self.read(identity)
        if day(current.get('as_of')) != today():
            raise InputError('Current input as_of must be today in UTC')
        if packet_binding(packet) != packet_binding(current):
            raise InputError('Requirements or source snapshot changed; generate and review a new draft')
        validate(current, output)
        if any('provenance' in source for source in packet['sources']):
            policy = self.db.execute('SELECT manifest_path FROM source_policies WHERE draft_id=?', (identity,)).fetchone()
            if not policy:
                raise InputError('GitHub draft has no bound operator policy; stage again')
            _, manifest = policy_file(policy[0])
            check_policy_binding(packet, manifest)

    def decide(self, identity, requirement, current, decision, expected_revision, note):
        if decision not in ('approve', 'reject'):
            raise InputError('Unknown decision')
        text(note, 'review note', 2000)
        rows, current = self.current_rows(identity, current)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.recheck_policy(identity, current)
            if requirement not in rows:
                raise InputError('Unknown requirement')
            if decision == 'approve' and rows[requirement]['status'] != 'supported':
                raise InputError('Only supported answers can be approved')
            previous = self.latest(identity, requirement)
            if expected_revision != (previous[0] if previous else 0):
                raise InputError('Review revision changed; inspect the latest decision before retrying')
            uid = os.getuid()
            cursor = self.db.execute('INSERT INTO decisions (draft_id,requirement_id,decision,reviewer_uid,reviewer_name,recorded_at,note) VALUES (?,?,?,?,?,?,?)',
                (identity, requirement, decision, uid, pwd.getpwuid(uid).pw_name,
                 datetime.now(timezone.utc).isoformat(), note))
            self.db.execute('COMMIT')
            return cursor.lastrowid
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def export(self, identity, current=None):
        rows, current = self.current_rows(identity, current)
        self.db.execute('BEGIN')
        try:
            self.recheck_policy(identity, current)
            approved = []
            for requirement, row in rows.items():
                decision = self.latest(identity, requirement)
                if row['status'] == 'supported' and decision and decision[1] == 'approve':
                    approved.append({**row, 'review_status': 'approved', 'revision': decision[0],
                                     'reviewer_uid': decision[2], 'reviewer_name': decision[3],
                                     'reviewed_at': decision[4], 'review_note': decision[5]})
            self.db.execute('COMMIT')
            return {'draft_id': identity, 'checked_at': datetime.now(timezone.utc).isoformat(),
                    'current_input_sha256': digest(current), 'approved_answers': approved,
                    'source_provenance': [{'id': source['id'], **source['provenance']} for source in current['sources'] if 'provenance' in source],
                    'withheld_count': len(rows) - len(approved)}
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def inspect(self, identity):
        _, output = self.read(identity)
        return [{'requirement_id': row['requirement_id'], 'status': row['status'],
                 'latest_decision': self.latest(identity, row['requirement_id'])} for row in output['matrix']]


def read_file(path, maximum=500000):
    """Bound inputs to 500 KB; stage imports use the shared serialized result cap.

    The result cap includes pretty-print whitespace and execution receipts,
    matching the CLI output boundary rather than its smaller input contract.
    """
    with open(path, 'rb') as handle:
        raw = handle.read(maximum + 1)
    if len(raw) > maximum:
        raise InputError(f'File exceeds {maximum} bytes')
    return loads(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    stage = sub.add_parser('stage'); stage.add_argument('--input', required=True); stage.add_argument('--result', required=True); stage.add_argument('--source-manifest', help='Private operator policy file required for GitHub-bound drafts')
    inspect = sub.add_parser('inspect'); inspect.add_argument('--draft', required=True)
    for command in ('decide', 'export'):
        item = sub.add_parser(command); item.add_argument('--draft', required=True); item.add_argument('--current-input', help='Required for manual drafts; forbidden for GitHub-bound drafts')
        if command == 'decide':
            item.add_argument('--requirement', required=True)
            item.add_argument('--decision', required=True, choices=['approve', 'reject'])
            item.add_argument('--expected-revision', required=True, type=int)
            item.add_argument('--note', required=True)
    args = parser.parse_args()
    ledger = None
    try:
        ledger = Ledger(args.db)
        if args.command == 'stage':
            result = {'draft_id': ledger.stage(read_file(args.input), read_file(args.result, MAX_RESULT_FILE_BYTES), args.source_manifest)}
        elif args.command == 'inspect':
            result = ledger.inspect(args.draft)
        elif args.command == 'decide':
            result = {'revision': ledger.decide(args.draft, args.requirement, read_file(args.current_input) if args.current_input else None, args.decision, args.expected_revision, args.note)}
        else:
            result = ledger.export(args.draft, read_file(args.current_input) if args.current_input else None)
        print(json.dumps(result, indent=2))
    except (InputError, OSError, sqlite3.Error, KeyError, TypeError) as exc:
        print('Review failed: ' + str(exc), file=sys.stderr)
        return 2
    finally:
        if ledger:
            ledger.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
