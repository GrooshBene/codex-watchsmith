import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_notifications import ROOT, module

D = module('watchsmith_delivery')
N = module('activitysmith_notify')


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.store = D.Store(self.home)
        self.addCleanup(self.store.close)
        self.key = D.event_key('thread', 'turn')

    def test_detail_acceptance_suppresses_generic(self):
        claim = self.store.claim(self.key, 'detail', now=100)
        self.assertTrue(self.store.finish(self.key, claim['token'], 'accepted', now=101))
        self.assertEqual(self.store.claim(self.key, 'generic', now=102)['action'], 'skip')
        self.assertEqual(self.store.claim(D.event_key('thread', 'other'), 'generic', now=102)['action'], 'send')

    def test_pending_failure_and_lease_expiry(self):
        claim = self.store.claim(self.key, 'detail', lease=10, now=100)
        self.assertEqual(self.store.claim(self.key, 'generic', now=105)['action'], 'wait')
        self.store.finish(self.key, claim['token'], 'failed', now=106)
        generic = self.store.claim(self.key, 'generic', now=107)
        self.assertEqual(generic['action'], 'send')
        self.assertFalse(self.store.finish(self.key, claim['token'], 'accepted', now=108))
        self.assertEqual(self.store.claim(self.key, 'generic', now=200)['action'], 'skip')
        other = D.event_key('thread', 'expired')
        self.store.claim(other, 'detail', lease=10, now=100)
        self.assertEqual(self.store.claim(other, 'generic', now=111)['action'], 'send')

    def test_unknown_and_generic_first_are_not_retried(self):
        claim = self.store.claim(self.key, 'generic', now=100)
        self.store.finish(self.key, claim['token'], 'unknown', now=101)
        for owner in ('detail', 'generic'):
            self.assertEqual(self.store.claim(self.key, owner, now=102)['action'], 'skip')

    def test_retention(self):
        claim = self.store.claim(self.key, 'generic', now=100)
        self.store.finish(self.key, claim['token'], 'accepted', now=101)
        self.assertEqual(self.store.claim(self.key, 'generic', now=102 + D.RETENTION)['action'], 'send')

    def test_simultaneous_process_claims(self):
        cmd = [sys.executable, str(ROOT / 'bin/watchsmith_delivery.py'), '--home', str(self.home), 'claim', '--thread-id', 'thread', '--turn-id', 'turn']
        processes = [subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(8)]
        outputs = []
        for p in processes:
            out, err = p.communicate(timeout=10)
            self.assertEqual(p.returncode, 0, err)
            outputs.append(json.loads(out)['action'])
        self.assertEqual(outputs.count('send'), 1)
        self.assertEqual(outputs.count('wait'), 7)

    def test_notifier_suppression_and_missing_identity_fallback(self):
        claim = self.store.claim(self.key, 'detail')
        self.store.finish(self.key, claim['token'], 'accepted')
        event = {'type': 'agent-turn-complete', 'thread-id': 'thread', 'turn-id': 'turn'}
        with patch.object(N, 'HOME', self.home), patch.object(N.shutil, 'which', return_value='/fake/cli'), patch.object(N, 'get_key', return_value='fake'), patch.object(N, 'deliver', return_value='accepted') as send:
            with patch.object(sys, 'argv', ['notify', json.dumps(event)]):
                N.main()
                send.assert_not_called()
            del event['turn-id']
            with patch.object(sys, 'argv', ['notify', json.dumps(event)]):
                N.main()
                send.assert_called_once()

    def test_unavailable_store_keeps_best_effort_completion(self):
        event = {'type': 'agent-turn-complete', 'thread-id': 'thread', 'turn-id': 'turn'}
        with patch.object(sys, 'argv', ['notify', json.dumps(event)]), patch.object(N, 'Store', side_effect=OSError()), patch.object(N.shutil, 'which', return_value='/fake/cli'), patch.object(N, 'get_key', return_value='fake'), patch.object(N, 'deliver', return_value='accepted') as send:
            self.assertEqual(N.main(), 0)
            send.assert_called_once()

    def test_invalid_identity_is_not_guessed(self):
        for turn in (None, '', [], ' '):
            with self.assertRaises(ValueError):
                D.event_key('thread', turn)

    def test_generic_senders_share_installed_database(self):
        import shutil
        bin_dir = self.home / 'bin'
        bin_dir.mkdir()
        for name in ('activitysmith_notify.py', 'watchsmith_delivery.py'):
            shutil.copy(ROOT / 'bin' / name, bin_dir / name)
        cli = bin_dir / 'activitysmith'
        log = self.home / 'calls'
        cli.write_text('#!' + sys.executable + '\nimport os,time\nfrom pathlib import Path\nwith Path(os.environ["TEST_CALLS"]).open("a") as f: f.write("push\\n")\ntime.sleep(.2)\nprint("Success: true")\n')
        cli.chmod(0o755)
        env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'], ACTIVITYSMITH_API_KEY='fake', TEST_CALLS=str(log))
        event = json.dumps({'type': 'agent-turn-complete', 'thread-id': 'thread', 'turn-id': 'turn'})
        cmd = [sys.executable, str(bin_dir / 'activitysmith_notify.py'), event]
        processes = [subprocess.Popen(cmd, env=env) for _ in range(3)]
        for p in processes:
            self.assertEqual(p.wait(timeout=10), 0)
        self.assertEqual(log.read_text().splitlines(), ['push'])


class SummaryRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.store = D.Store(self.home)
        self.addCleanup(self.store.close)
        self.preview = {'title': '알림 개선 · 완료', 'message': '작업명과 결과 요약 표시를 구현했습니다.', 'subtitle': '검증: 자동 테스트 통과'}

    def event(self, staged, thread='thread', turn='turn'):
        return {'type': 'agent-turn-complete', 'thread-id': thread, 'turn-id': turn,
                'last-assistant-message': 'PRIVATE raw response\n' + (staged['final_marker'] or '')}

    def test_explicit_reference_binds_only_matching_thread_and_turn(self):
        queued = self.store.stage('thread', self.preview)
        self.assertIsNone(self.store.summary(self.event(queued, thread='other')))
        key, payload = self.store.summary(self.event(queued))
        self.assertEqual(payload, self.preview)
        self.assertEqual(key, D.event_key('thread', 'turn'))
        self.assertIsNone(self.store.summary(self.event(queued, turn='other')))
        self.assertEqual(self.store.summary(self.event(queued))[1], self.preview)

    def test_exact_identity_needs_no_marker_and_never_selects_latest(self):
        self.store.stage('thread', self.preview, 'turn')
        self.assertIsNone(self.store.summary({'thread-id': 'thread', 'turn-id': 'other'}))
        self.assertEqual(self.store.summary({'thread-id': 'thread', 'turn-id': 'turn'})[1], self.preview)
        self.store.stage('thread', self.preview, 'turn')
        self.assertIsNone(self.store.summary({'thread-id': 'thread', 'turn-id': 'turn'}))

    def test_missing_marker_and_expired_summary_fall_back(self):
        queued = self.store.stage('thread', self.preview, now=100)
        self.assertIsNone(self.store.summary({'thread-id': 'thread', 'turn-id': 'turn'}, now=101))
        self.assertIsNone(self.store.summary(self.event(queued), now=100 + D.SUMMARY_TTL + 1))
        event = self.event(queued)
        event['last-assistant-message'] += '\nquoted elsewhere'
        self.assertIsNone(self.store.summary(event, now=101))

    def test_marker_can_correlate_without_turn_but_not_without_thread(self):
        queued = self.store.stage('thread', self.preview)
        event = self.event(queued, turn=None)
        first = self.store.summary(event)
        self.assertIsNotNone(first)
        self.assertEqual(first, self.store.summary(event))
        event.pop('thread-id')
        self.assertIsNone(self.store.summary(event))

    def test_hook_sends_reviewed_summary_once_without_raw_response(self):
        queued = self.store.stage('thread', self.preview)
        event = self.event(queued)
        with patch.object(N, 'HOME', self.home), patch.object(N.shutil, 'which', return_value='/fake/cli'), patch.object(N, 'get_key', return_value='fake'), patch.object(N, 'deliver', return_value='accepted') as send:
            for _ in range(2):
                with patch.object(sys, 'argv', ['notify', json.dumps(event)]):
                    N.main()
            send.assert_called_once_with('/fake/cli', 'fake', self.preview)
            self.assertNotIn('PRIVATE', str(send.call_args))

    def test_unknown_mcp_delivery_does_not_trigger_second_push(self):
        key = D.event_key('thread', 'turn')
        claim = self.store.claim(key, 'detail')
        self.store.finish(key, claim['token'], 'unknown')
        self.assertEqual(self.store.claim(key, 'generic')['action'], 'skip')

    def test_summary_and_generic_workers_share_one_claim(self):
        queued = self.store.stage('thread', self.preview)
        key, _ = self.store.summary(self.event(queued))
        claim = self.store.claim(key, 'generic')
        self.store.finish(key, claim['token'], 'accepted')
        self.assertEqual(self.store.claim(D.event_key('thread', 'turn'), 'generic')['action'], 'skip')

    def test_concurrent_installed_notifiers_send_only_preview(self):
        import shutil
        binary = self.home / 'bin'
        binary.mkdir()
        for name in ('activitysmith_notify.py', 'watchsmith_delivery.py'):
            shutil.copy(ROOT / 'bin' / name, binary / name)
        cli = binary / 'activitysmith'
        log = self.home / 'pushes.jsonl'
        cli.write_text('#!' + sys.executable + '\nimport os,sys,json\nwith open(os.environ["TEST_CALLS"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\nprint("Success: true")\n')
        cli.chmod(0o755)
        queued = self.store.stage('thread', self.preview)
        event = json.dumps(self.event(queued))
        env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'], ACTIVITYSMITH_API_KEY='fake', TEST_CALLS=str(log))
        workers = [subprocess.Popen([sys.executable, str(binary / 'activitysmith_notify.py'), event], env=env) for _ in range(3)]
        for worker in workers:
            self.assertEqual(worker.wait(timeout=10), 0)
        lines = log.read_text().splitlines()
        self.assertEqual(len(lines), 1)
        args = json.loads(lines[0])
        self.assertIn(self.preview['title'], args)
        self.assertIn(self.preview['message'], args)
        self.assertIn(self.preview['subtitle'], args)
        self.assertNotIn('PRIVATE', str(args))
