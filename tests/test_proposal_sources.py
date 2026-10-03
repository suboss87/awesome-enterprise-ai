import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from datetime import timedelta

from enterprise_ai import proposal_sources as ps
from enterprise_ai.proposal_review import Ledger, today
from enterprise_ai.catalog import load
from enterprise_ai.common import InputError, ReplayAI

TEXT = 'The Enterprise plan supports SAML single sign-on.'
RAW = TEXT.encode()
BLOB = hashlib.sha1(b'blob '+str(len(RAW)).encode()+b'\0'+RAW).hexdigest()
HEAD = 'a'*40
TREE = 'b'*40
REQUIREMENTS = [{'id': 'req-1', 'text': 'Does the Enterprise plan support SAML?'}]


def manifest():
    return {'version': 1, 'repositories': [{'owner': 'org', 'repo': 'docs', 'repository_id': 1, 'branch': 'main'}],
            'sources': [{'id': 'doc-1', 'repository_id': 1, 'path': 'sso.md', 'approved_blob_sha': BLOB,
                         'approval': 'approved', 'valid_from': (today()-timedelta(days=1)).isoformat(),
                         'valid_until': (today()+timedelta(days=1)).isoformat()}]}


class FixtureGitHub:
    def __init__(self):
        self.calls = []
        self.changed_head = False
        self.refs = 0
        self.responses = {
            '/repos/org/docs': {'id': 1, 'full_name': 'org/docs'},
            '/repos/org/docs/git/commits/'+HEAD: {'sha': HEAD, 'tree': {'sha': TREE}},
            '/repos/org/docs/git/trees/'+TREE: {'sha': TREE, 'truncated': False,
                'tree': [{'path': 'sso.md', 'type': 'blob', 'mode': '100644', 'sha': BLOB, 'size': len(RAW)}]},
            '/repos/org/docs/contents/sso.md?ref='+HEAD: {'type': 'file', 'path': 'sso.md', 'sha': BLOB,
                'encoding': 'base64', 'size': len(RAW), 'content': base64.b64encode(RAW).decode(),
                'download_url': 'https://evil.invalid/must-not-be-followed'}}

    def get(self, endpoint):
        self.calls.append(endpoint)
        if '/git/ref/heads/' in endpoint:
            self.refs += 1
            return {'object': {'type': 'commit', 'sha': 'c'*40 if self.changed_head and self.refs>1 else HEAD}}
        return copy.deepcopy(self.responses[endpoint])


class SourceTests(unittest.TestCase):
    def test_regular_source_has_bound_provenance_and_no_download_request(self):
        client = FixtureGitHub()
        packet = ps._collect(manifest(), REQUIREMENTS, client)
        source = packet['sources'][0]
        self.assertEqual(TEXT, source['text'])
        self.assertEqual(HEAD, source['provenance']['commit_sha'])
        self.assertEqual(BLOB, source['provenance']['blob_sha'])
        self.assertEqual(ps.digest(manifest()), source['provenance']['manifest_sha256'])
        self.assertFalse(any('evil' in url for url in client.calls))

    def test_path_allowlist_validation_before_credentials_or_network(self):
        for value in ('../sso.md', '/sso.md', 'x//sso.md', 'x%2Fsso.md', 'https://evil/x', 'x\\sso.md'):
            policy = manifest(); policy['sources'][0]['path'] = value
            with patch.object(ps, '_run_refresh') as worker, self.assertRaises(InputError):
                ps.collect(policy, REQUIREMENTS)
            worker.assert_not_called()

    def test_identity_symlink_submodule_and_truncation_fail_closed(self):
        for change in ('repo', 'symlink', 'submodule', 'truncated', 'missing'):
            client = FixtureGitHub(); tree = client.responses['/repos/org/docs/git/trees/'+TREE]
            if change == 'repo': client.responses['/repos/org/docs']['id'] = 2
            elif change == 'symlink': tree['tree'][0]['mode'] = '120000'
            elif change == 'submodule': tree['tree'][0].update(mode='160000', type='commit')
            elif change == 'truncated': tree['truncated'] = True
            else: tree['tree'] = []
            with self.subTest(change=change), self.assertRaises(InputError):
                ps._collect(manifest(), REQUIREMENTS, client)
            self.assertFalse(any('/contents/' in call for call in client.calls))

    def test_content_integrity_metadata_and_limits(self):
        for field, value in [('content', '!bad-base64!'), ('content', base64.b64encode(b'\xff').decode()),
                             ('content', base64.b64encode(b'Altered text').decode()), ('size', 1),
                             ('sha', 'f'*40), ('path', 'other.md'), ('encoding', 'none')]:
            client = FixtureGitHub()
            client.responses['/repos/org/docs/contents/sso.md?ref='+HEAD][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(InputError):
                ps._collect(manifest(), REQUIREMENTS, client)
        client = FixtureGitHub()
        client.responses['/repos/org/docs/git/trees/'+TREE]['tree'][0]['size'] = ps.MAX_FILE+1
        with self.assertRaises(InputError): ps._collect(manifest(), REQUIREMENTS, client)

    def test_manifest_blob_and_branch_races_rejected(self):
        policy = manifest(); policy['sources'][0]['approved_blob_sha'] = 'f'*40
        with self.assertRaises(InputError): ps._collect(policy, REQUIREMENTS, FixtureGitHub())
        client = FixtureGitHub(); client.changed_head = True
        with self.assertRaises(InputError): ps._collect(manifest(), REQUIREMENTS, client)

    def test_transport_404_is_not_deletion_and_redirect_refused(self):
        import urllib.error
        client = ps.GitHub.__new__(ps.GitHub)
        client.token = 'fixture-token'; client.deadline = time.monotonic()+10
        from unittest.mock import Mock
        client.opener = Mock()
        for code in (401, 403, 404, 429):
            client.opener.open.side_effect = urllib.error.HTTPError('https://api.github.com/repos/org/docs', code, 'ignored', {}, None)
            with self.subTest(code=code), self.assertRaises(InputError) as error:
                client.get('/repos/org/docs')
            self.assertNotIn('fixture-token', str(error.exception))
            if code == 404: self.assertIn('deletion is not established', str(error.exception))
        with self.assertRaises(InputError):
            ps.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.invalid')

    def test_worker_deadline_terminates_and_reaps_slow_process(self):
        started = time.monotonic()
        with self.assertRaises(InputError):
            ps._run_refresh([sys.executable, '-c', 'import time;time.sleep(30)'], b'', timeout=0.1)
        self.assertLess(time.monotonic()-started, 3)

    def test_failed_selector_setup_still_reaps_child(self):
        started = []
        original = subprocess.Popen
        def capture(*args, **kwargs):
            child = original(*args, **kwargs); started.append(child); return child
        with patch.object(ps.subprocess, 'Popen', side_effect=capture), patch.object(ps.selectors, 'DefaultSelector', side_effect=OSError('fixture failure')):
            with self.assertRaises(OSError):
                ps._run_refresh([sys.executable, '-c', 'import time;time.sleep(30)'], b'', timeout=5)
        self.assertEqual(1, len(started))
        self.assertIsNotNone(started[0].poll())
        self.assertTrue(started[0].stdin.closed and started[0].stdout.closed)

    def test_worker_output_is_capped_before_process_completion(self):
        code = "import os,time;os.write(1,b'x'*1000001);time.sleep(30)"
        started = time.monotonic()
        with self.assertRaisesRegex(InputError, 'response exceeds'):
            ps._run_refresh([sys.executable, '-c', code], b'', timeout=5)
        self.assertLess(time.monotonic()-started, 3)

    def test_worker_stderr_is_discarded_and_payload_is_streamed(self):
        code = "import os,sys;os.write(2,b'x'*2000000);data=sys.stdin.buffer.read();sys.stdout.buffer.write(data)"
        payload = b'p'*400000
        status, output = ps._run_refresh([sys.executable, '-c', code], payload, timeout=5)
        self.assertEqual((0, payload), (status, output))

    def test_malformed_worker_response_is_sanitized(self):
        with patch.object(ps, '_run_refresh', return_value=(2, b'{"error":"Malformed or unavailable GitHub source"}')):
            with self.assertRaisesRegex(InputError, 'Malformed'):
                ps.collect(manifest(), REQUIREMENTS)


class BoundLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.policy_path = self.root/'manifest.json'; self.policy = manifest()
        self.policy_path.write_text(json.dumps(self.policy))
        self.ledger = Ledger(self.root/'reviews.sqlite')
        self.packet = ps._collect(self.policy, REQUIREMENTS, FixtureGitHub())
        response = {'answers': [{'requirement_id': 'req-1', 'status': 'supported', 'draft': TEXT,
                                'evidence': [{'source_id': 'doc-1', 'quote': TEXT}]}]}
        self.output = load('proposal-operations').run(self.packet, ReplayAI([response]))
        self.refresh = patch('enterprise_ai.proposal_review.proposal_sources.collect',
                             side_effect=lambda policy, reqs: ps._collect(policy, reqs, FixtureGitHub()))
        self.mock = self.refresh.start()
        self.identity = self.ledger.stage(self.packet, self.output, self.policy_path)

    def tearDown(self):
        self.refresh.stop(); self.ledger.close(); self.tmp.cleanup()

    def test_programmatic_approve_export_requires_live_refresh(self):
        self.ledger.decide(self.identity, 'req-1', None, 'approve', 0, 'Verified source and answer')
        self.assertEqual(1, len(self.ledger.export(self.identity)['approved_answers']))
        self.assertEqual(3, self.mock.call_count)  # stage, approve, export
        self.mock.side_effect = InputError('GitHub unavailable')
        with self.assertRaises(InputError): self.ledger.export(self.identity)

    def test_source_refresh_does_not_lock_unrelated_local_decisions(self):
        manual = copy.deepcopy(self.packet)
        del manual['sources'][0]['provenance']
        local_id = self.ledger.stage(manual, self.output)
        peer = Ledger(self.root/'reviews.sqlite')
        self.addCleanup(peer.close)
        peer.db.execute('PRAGMA busy_timeout=50')
        completed = []
        def refresh(policy, requirements):
            previous = peer.latest(local_id, 'req-1')
            peer.decide(local_id, 'req-1', manual, 'approve', previous[0] if previous else 0, 'Independent local review')
            completed.append(True)
            return ps._collect(policy, requirements, FixtureGitHub())
        self.mock.side_effect = refresh
        self.ledger.decide(self.identity, 'req-1', None, 'approve', 0, 'Verified')
        self.ledger.export(self.identity)
        self.assertEqual(2, len(completed))

    def test_policy_rechecked_after_refresh_before_transaction_decision(self):
        original = self.ledger.current_rows
        def revoke_after_refresh(*args):
            result = original(*args)
            revoked = copy.deepcopy(self.policy); revoked['sources'][0]['approval'] = 'revoked'
            self.policy_path.write_text(json.dumps(revoked))
            return result
        with patch.object(self.ledger, 'current_rows', side_effect=revoke_after_refresh):
            with self.assertRaises(InputError):
                self.ledger.decide(self.identity, 'req-1', None, 'approve', 0, 'Stale policy')
        self.assertIsNone(self.ledger.latest(self.identity, 'req-1'))

    def test_utc_day_change_after_refresh_blocks_decision_and_export(self):
        original = self.ledger.current_rows
        tomorrow = today()+timedelta(days=1)
        for operation in ('decide', 'export'):
            clock_patch = patch('enterprise_ai.proposal_review.today', return_value=tomorrow)
            def cross_midnight(*args):
                result = original(*args)
                clock_patch.start()
                return result
            try:
                with patch.object(self.ledger, 'current_rows', side_effect=cross_midnight):
                    with self.subTest(operation=operation), self.assertRaisesRegex(InputError, 'today'):
                        if operation == 'decide':
                            self.ledger.decide(self.identity, 'req-1', None, 'approve', 0, 'Yesterday')
                        else:
                            self.ledger.export(self.identity)
            finally:
                clock_patch.stop()
            self.assertIsNone(self.ledger.latest(self.identity, 'req-1'))

    def test_manual_input_cannot_bypass_stored_github_binding(self):
        for current in (self.packet, {**self.packet, 'sources': []}):
            with self.assertRaises(InputError): self.ledger.export(self.identity, current)
            with self.assertRaises(InputError):
                self.ledger.decide(self.identity, 'req-1', current, 'approve', 0, 'Bypass attempt')

    def test_policy_revocation_and_replacement_path_are_rejected(self):
        self.ledger.decide(self.identity, 'req-1', None, 'approve', 0, 'Verified')
        other = self.root/'other.json'; other.write_text(json.dumps(self.policy))
        with self.assertRaises(InputError): self.ledger.stage(self.packet, self.output, other)
        self.policy['sources'][0]['approval'] = 'revoked'
        self.policy_path.write_text(json.dumps(self.policy))
        with self.assertRaises(InputError): self.ledger.export(self.identity)
        self.assertEqual('approve', self.ledger.latest(self.identity, 'req-1')[1])

    def test_policy_scope_expansion_is_rejected_before_network(self):
        self.policy['repositories'][0]['repo'] = 'unauthorized-other-repo'
        self.policy_path.write_text(json.dumps(self.policy))
        calls = self.mock.call_count
        with self.assertRaises(InputError): self.ledger.export(self.identity)
        self.assertEqual(calls, self.mock.call_count)

    def test_new_branch_head_invalidates_even_when_source_text_unchanged(self):
        self.ledger.decide(self.identity, 'req-1', None, 'approve', 0, 'Verified')
        changed = copy.deepcopy(self.packet)
        changed['sources'][0]['provenance']['commit_sha'] = 'f'*40
        self.mock.side_effect = None; self.mock.return_value = changed
        with self.assertRaises(InputError): self.ledger.export(self.identity)

    def test_policy_revoked_during_refresh_blocks_stage_decide_and_export(self):
        self.ledger.decide(self.identity, 'req-1', None, 'approve', 0, 'Initially verified')
        original_revision = self.ledger.latest(self.identity, 'req-1')[0]
        def revoke_during_refresh(policy, reqs):
            result = ps._collect(policy, reqs, FixtureGitHub())
            revoked = copy.deepcopy(policy)
            revoked['sources'][0]['approval'] = 'revoked'
            self.policy_path.write_text(json.dumps(revoked))
            return result
        self.mock.side_effect = revoke_during_refresh
        for operation in ('stage', 'decide', 'export'):
            self.policy_path.write_text(json.dumps(self.policy))
            with self.subTest(operation=operation), self.assertRaises(InputError):
                if operation == 'stage':
                    output = copy.deepcopy(self.output)
                    output['summary'] = 'Distinct candidate to ensure no new row is inserted'
                    self.ledger.stage(self.packet, output, self.policy_path)
                elif operation == 'decide':
                    self.ledger.decide(self.identity, 'req-1', None, 'approve', original_revision, 'Stale approval attempt')
                else:
                    self.ledger.export(self.identity)
            self.assertEqual(original_revision, self.ledger.latest(self.identity, 'req-1')[0])
            self.assertEqual(1, self.ledger.db.execute('SELECT count(*) FROM drafts').fetchone()[0])

    def test_source_provenance_cannot_be_removed_from_current_packet(self):
        packet = copy.deepcopy(self.packet); del packet['sources'][0]['provenance']
        with self.assertRaises(InputError): self.ledger.export(self.identity, packet)

    def test_staging_needs_policy_and_current_source(self):
        with self.assertRaises(InputError): self.ledger.stage(self.packet, self.output)
        self.mock.side_effect = InputError('Unverified current source')
        with self.assertRaises(InputError): self.ledger.stage(self.packet, self.output, self.policy_path)

    def test_policy_symlink_and_untrusted_write_permissions_rejected(self):
        self.policy_path.chmod(0o666)
        with self.assertRaises(InputError): self.ledger.export(self.identity)
        self.policy_path.chmod(0o600)
        original = self.root/'original.json'; self.policy_path.rename(original)
        self.policy_path.symlink_to(original)
        with self.assertRaises(OSError): self.ledger.export(self.identity)


if __name__ == '__main__': unittest.main()
