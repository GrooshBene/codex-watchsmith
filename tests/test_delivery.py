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
