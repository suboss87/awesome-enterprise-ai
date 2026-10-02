"""Local, OS-account-bound proposal review ledger. No network or enterprise identity."""
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

from .catalog import load
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
            CREATE TABLE IF NOT EXISTS decisions (
              sequence INTEGER PRIMARY KEY AUTOINCREMENT,
              draft_id TEXT NOT NULL REFERENCES drafts(id), requirement_id TEXT NOT NULL,
              decision TEXT NOT NULL CHECK(decision IN ('approve','reject')),
              reviewer_uid INTEGER NOT NULL, reviewer_name TEXT NOT NULL,
              recorded_at TEXT NOT NULL, note TEXT NOT NULL);
        ''')

    def close(self):
        self.db.close()

    def stage(self, packet, output):
        validate(packet, output)
        identity = digest({'packet': packet, 'output': output})
        self.db.execute('INSERT OR IGNORE INTO drafts VALUES (?,?,?)',
                        (identity, canonical(packet), canonical(output)))
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
        if day(current.get('as_of')) != today():
            raise InputError('Current input as_of must be today in UTC')
        if packet_binding(packet) != packet_binding(current):
            raise InputError('Requirements or source snapshot changed; generate and review a new draft')
        # Re-evaluate actual validity today, never the historical generation date.
        validate(current, output)
        return {row['requirement_id']: row for row in output['matrix']}

    def latest(self, identity, requirement):
        return self.db.execute('''SELECT sequence,decision,reviewer_uid,reviewer_name,recorded_at,note
            FROM decisions WHERE draft_id=? AND requirement_id=? ORDER BY sequence DESC LIMIT 1''',
            (identity, requirement)).fetchone()

    def decide(self, identity, requirement, current, decision, expected_revision, note):
        if decision not in ('approve', 'reject'):
            raise InputError('Unknown decision')
        text(note, 'review note', 2000)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            rows = self.current_rows(identity, current)
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

    def export(self, identity, current):
        self.db.execute('BEGIN')
        try:
            rows = self.current_rows(identity, current)
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
                    'withheld_count': len(rows) - len(approved)}
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def inspect(self, identity):
        _, output = self.read(identity)
        return [{'requirement_id': row['requirement_id'], 'status': row['status'],
                 'latest_decision': self.latest(identity, row['requirement_id'])} for row in output['matrix']]


def read_file(path):
    with open(path, 'rb') as handle:
        raw = handle.read(500001)
    if len(raw) > 500000:
        raise InputError('File exceeds 500 KB')
    return loads(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    stage = sub.add_parser('stage'); stage.add_argument('--input', required=True); stage.add_argument('--result', required=True)
    inspect = sub.add_parser('inspect'); inspect.add_argument('--draft', required=True)
    for command in ('decide', 'export'):
        item = sub.add_parser(command); item.add_argument('--draft', required=True); item.add_argument('--current-input', required=True)
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
            result = {'draft_id': ledger.stage(read_file(args.input), read_file(args.result))}
        elif args.command == 'inspect':
            result = ledger.inspect(args.draft)
        elif args.command == 'decide':
            result = {'revision': ledger.decide(args.draft, args.requirement, read_file(args.current_input), args.decision, args.expected_revision, args.note)}
        else:
            result = ledger.export(args.draft, read_file(args.current_input))
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
