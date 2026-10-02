import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

from enterprise_ai.catalog import load
from enterprise_ai.common import InputError, ReplayAI
from enterprise_ai.proposal_review import Ledger, today, read_file
from enterprise_ai.execution import MAX_RESULT_FILE_BYTES

ROOT = Path(__file__).resolve().parents[1]


class ProposalReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'review.sqlite'
        self.ledger = Ledger(self.path)
        self.packet = json.loads((ROOT / 'projects/proposal-operations/examples/input.json').read_text())
        self.packet['as_of'] = today().isoformat()
        self.packet['sources'][0]['valid_from'] = (today() - timedelta(days=1)).isoformat()
        self.packet['sources'][0]['valid_until'] = (today() + timedelta(days=1)).isoformat()
        self.responses = json.loads((ROOT / 'projects/proposal-operations/examples/responses.json').read_text())
        self.output = load('proposal-operations').run(self.packet, ReplayAI(self.responses))
        self.identity = self.ledger.stage(self.packet, self.output)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def approve(self):
        return self.ledger.decide(self.identity, 'req-1', self.packet, 'approve', 0, 'Checked the plan restriction and source quotation.')

    def test_durable_approve_export_reject(self):
        self.assertEqual([], self.ledger.export(self.identity, self.packet)['approved_answers'])
        revision = self.approve()
        self.ledger.close()
        self.ledger = Ledger(self.path)
        result = self.ledger.export(self.identity, self.packet)
        self.assertEqual('approved', result['approved_answers'][0]['review_status'])
        self.ledger.decide(self.identity, 'req-1', self.packet, 'reject', revision, 'Reconsidered the wording.')
        self.assertEqual([], self.ledger.export(self.identity, self.packet)['approved_answers'])
        self.assertEqual(2, self.ledger.db.execute('SELECT count(*) FROM decisions').fetchone()[0])

    def test_changed_inputs_cannot_reuse_approval(self):
        self.approve()
        for field, value in [('text', 'Changed capability'), ('approval', 'revoked'), ('approval', 'superseded')]:
            current = copy.deepcopy(self.packet)
            current['sources'][0][field] = value
            with self.assertRaises(InputError):
                self.ledger.export(self.identity, current)
        current = copy.deepcopy(self.packet)
        current['requirements'][0]['text'] = 'Changed question'
        with self.assertRaises(InputError):
            self.ledger.export(self.identity, current)

    def test_added_source_invalidates(self):
        self.approve()
        current = copy.deepcopy(self.packet)
        current['sources'].append({**current['sources'][0], 'id': 'contradiction'})
        with self.assertRaises(InputError):
            self.ledger.export(self.identity, current)

    def test_expiry_and_stale_as_of(self):
        from unittest.mock import patch
        self.approve()
        later = today() + timedelta(days=2)
        with patch('enterprise_ai.proposal_review.today', return_value=later):
            with self.assertRaises(InputError):
                self.ledger.export(self.identity, self.packet)
            current = {**self.packet, 'as_of': later.isoformat()}
            with self.assertRaises(InputError):
                self.ledger.export(self.identity, current)

    def test_changed_draft_needs_fresh_decision(self):
        self.approve()
        output = copy.deepcopy(self.output)
        output['matrix'][0]['draft'] = 'Different human-reviewable wording'
        identity = self.ledger.stage(self.packet, output)
        self.assertNotEqual(identity, self.identity)
        self.assertEqual([], self.ledger.export(identity, self.packet)['approved_answers'])

    def test_tampered_persisted_binding_rejected(self):
        self.approve()
        self.ledger.db.execute('UPDATE drafts SET output=? WHERE id=?', ('{}', self.identity))
        with self.assertRaises(InputError):
            self.ledger.export(self.identity, self.packet)

    def test_invalid_citation_or_requirement_binding_rejected(self):
        for key, value in [('requirement', 'Another question'), ('evidence', [{'source_id': 'doc-1', 'quote': 'Fabricated fact'}])]:
            output = copy.deepcopy(self.output)
            output['matrix'][0][key] = value
            with self.assertRaises(InputError):
                self.ledger.stage(self.packet, output)

    def test_gap_and_conflict_cannot_be_approved(self):
        for status in ('gap', 'conflict'):
            packet = copy.deepcopy(self.packet)
            evidence = []
            if status == 'conflict':
                packet['sources'].append({**packet['sources'][0], 'id': 'doc-2'})
                evidence = [{'source_id': s['id'], 'quote': s['text']} for s in packet['sources']]
            output = load('proposal-operations').run(packet, ReplayAI([{'answers': [{'requirement_id': 'req-1', 'status': status, 'draft': '', 'evidence': evidence}]}]))
            identity = self.ledger.stage(packet, output)
            with self.assertRaises(InputError):
                self.ledger.decide(identity, 'req-1', packet, 'approve', 0, 'Cannot approve unresolved answer.')

    def test_concurrent_decisions_use_optimistic_revision(self):
        def decide(decision):
            ledger = Ledger(self.path)
            try:
                ledger.decide(self.identity, 'req-1', self.packet, decision, 0, 'Concurrent review')
                return True
            except InputError:
                return False
            finally:
                ledger.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(decide, ['approve', 'reject']))
        self.assertEqual([False, True], sorted(results))
        self.assertEqual(1, self.ledger.db.execute('SELECT count(*) FROM decisions').fetchone()[0])

    def test_failed_revision_rolls_back(self):
        revision = self.approve()
        with self.assertRaises(InputError):
            self.ledger.decide(self.identity, 'req-1', self.packet, 'reject', 0, 'Stale review')
        self.assertEqual(revision, self.ledger.latest(self.identity, 'req-1')[0])

    def test_revoked_and_superseded_evidence_withheld(self):
        for state in ('revoked', 'superseded'):
            packet = copy.deepcopy(self.packet)
            packet['sources'][0]['approval'] = state
            output = load('proposal-operations').run(packet, ReplayAI(self.responses))
            self.assertEqual('evidence_review', output['matrix'][0]['status'])
            identity = self.ledger.stage(packet, output)
            with self.assertRaises(InputError):
                self.ledger.decide(identity, 'req-1', packet, 'approve', 0, 'Must remain withheld')
            self.assertEqual([], self.ledger.export(identity, packet)['approved_answers'])

    def test_large_actual_cli_result_can_be_staged(self):
        packet = copy.deepcopy(self.packet)
        packet['sources'][0]['text'] = 'Approved capability: ' + 'x' * 8000
        packet['requirements'] = [{'id': f'req-{index}', 'text': 'Describe the approved capability.'}
                                  for index in range(100)]
        answer = {'answers': [{'requirement_id': requirement['id'], 'status': 'supported',
                  'draft': 'Capability is documented for human verification.',
                  'evidence': [{'source_id': packet['sources'][0]['id'],
                                'quote': packet['sources'][0]['text']}]}
                 for requirement in packet['requirements']]}
        input_path = Path(self.tmp.name) / 'input.json'
        response_path = Path(self.tmp.name) / 'responses.json'
        result_path = Path(self.tmp.name) / 'result.json'
        input_path.write_text(json.dumps(packet))
        response_path.write_text(json.dumps([answer]))
        # Exercise real worker + CLI pretty output, not only an in-memory workflow result.
        run = subprocess.run([sys.executable, '-m', 'enterprise_ai', 'run',
            'proposal-operations', '--input', str(input_path), '--mode', 'replay',
            '--responses', str(response_path)], cwd=ROOT, capture_output=True, timeout=30)
        self.assertEqual(0, run.returncode, run.stderr.decode())
        self.assertGreater(len(run.stdout), 500000)
        self.assertLessEqual(len(run.stdout), MAX_RESULT_FILE_BYTES)
        result_path.write_bytes(run.stdout)
        stage = subprocess.run([sys.executable, '-m', 'enterprise_ai.proposal_review',
            '--db', str(self.path), 'stage', '--input', str(input_path),
            '--result', str(result_path)], cwd=ROOT, capture_output=True, timeout=30)
        self.assertEqual(0, stage.returncode, stage.stderr.decode())
        identity = json.loads(stage.stdout)['draft_id']
        stored_packet, stored_result = self.ledger.read(identity)
        self.assertEqual(packet, stored_packet)
        self.assertEqual(100, len(stored_result['matrix']))

    def test_result_and_input_read_bounds_are_separate(self):
        path = Path(self.tmp.name) / 'oversized.json'
        with path.open('wb') as handle:
            handle.truncate(MAX_RESULT_FILE_BYTES + 1)
        with self.assertRaisesRegex(InputError, 'File exceeds'):
            read_file(path, MAX_RESULT_FILE_BYTES)
        with path.open('wb') as handle:
            handle.truncate(500001)
        with self.assertRaisesRegex(InputError, 'File exceeds'):
            read_file(path)

    def test_public_database_permissions_rejected(self):
        self.path.chmod(0o644)
        with self.assertRaises(InputError):
            Ledger(self.path)
        self.path.chmod(0o600)


if __name__ == '__main__':
    unittest.main()
