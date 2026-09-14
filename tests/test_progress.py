import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_notifications import ROOT, module

P = module('watchsmith_progress')


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='progress test ')
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.json'
        self.path.write_text(json.dumps(dict(stream_key='watchsmith-test', closed=False,
            token='', pending_until=0, semantic_active=False,
            may_have_stream=False, fallback_attempted=False)))

    def test_accepted_mcp_suppresses_watchdog(self):
        token = P.claim(self.path)['token']
        self.assertTrue(P.finish(self.path, token, 'accepted'))
        with patch.object(P, 'invoke') as call:
            P.fallback(self.path, 'cli', {})
            call.assert_not_called()

    def test_pending_then_failed_allows_fallback_once(self):
        token = P.claim(self.path, now=100)['token']
        with patch.object(P, 'invoke', return_value=None) as call:
            P.fallback(self.path, 'cli', {}, now=110)
            call.assert_not_called()
            P.finish(self.path, token, 'failed')
            P.fallback(self.path, 'cli', {}, now=111)
            P.fallback(self.path, 'cli', {}, now=112)
            self.assertEqual(call.call_count, 2)
            self.assertEqual(call.call_args.args[1][0], 'push')

    def test_expired_claim_and_late_ack(self):
        token = P.claim(self.path, now=100)['token']
        with patch.object(P, 'invoke', return_value=subprocess.CompletedProcess([], 0)) as call:
            P.fallback(self.path, 'cli', {}, now=200)
            self.assertEqual(call.call_args.args[1][2], 'watchsmith-test')
        self.assertFalse(P.finish(self.path, token, 'accepted'))
        self.assertEqual(P.claim(self.path, now=201)['stream_key'], 'watchsmith-test')

    def test_unknown_stream_does_not_send_extra_push(self):
        token = P.claim(self.path)['token']
        P.finish(self.path, token, 'unknown')
        with patch.object(P, 'invoke', return_value=None) as call:
            P.fallback(self.path, 'cli', {})
            self.assertEqual(call.call_count, 1)

    def test_closed_run_rejects_claim_and_ends_same_key(self):
        token = P.claim(self.path)['token']
        P.finish(self.path, token, 'accepted')
        with patch.object(P, 'invoke') as call:
            P.close_run(self.path, 'cli', {}, 1)
            self.assertEqual(call.call_args.args[1][2], 'watchsmith-test')
            self.assertNotIn('완료', call.call_args.args[1][-1])
            payload = json.loads(call.call_args.args[1][-1])
            self.assertEqual(payload['auto_dismiss_minutes'], 0)
            self.assertEqual(payload['percentage'], 0)
        self.assertEqual(P.claim(self.path)['action'], 'skip')

    def test_agent_end_prevents_duplicate_end_and_fallback(self):
        token = P.claim(self.path)['token']
        P.finish(self.path, token, 'accepted')
        P.ended(self.path)
        with patch.object(P, 'invoke') as call:
            P.fallback(self.path, 'cli', {})
            P.close_run(self.path, 'cli', {}, 0)
            call.assert_not_called()

    def test_concurrent_agents_only_one_claim(self):
        env = dict(os.environ, WATCHSMITH_PROGRESS_CONTEXT=str(self.path))
        children = [subprocess.Popen([sys.executable, str(ROOT / 'bin/watchsmith_progress.py'), 'claim'],
                    env=env, stdout=subprocess.PIPE, text=True) for _ in range(5)]
        actions = [json.loads(p.communicate(timeout=10)[0])['action'] for p in children]
        self.assertEqual(actions.count('send'), 1)
        self.assertEqual(actions.count('wait'), 4)

    def wrapper(self, code, stream=True, threshold='.1'):
        directory = Path(self.tmp.name)
        cli = directory / 'activitysmith'
        log = directory / 'calls'
        cli.write_text('#!' + sys.executable + '\nimport json,sys,os\n'
            'with open(os.environ["TEST_CALLS"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
            + ('sys.exit(1 if "--help" in sys.argv else 0)\n' if not stream else 'print("Success: true")\n'))
        cli.chmod(0o755)
        env = dict(os.environ, PATH=str(directory) + os.pathsep + os.environ['PATH'],
                   TEST_CALLS=str(log), ACTIVITYSMITH_API_KEY='fake',
                   CODEX_WATCH_THRESHOLD_SECONDS=threshold)
        result = subprocess.run([str(ROOT / 'bin/codex-watch'), sys.executable, '-c', code],
                                env=env, capture_output=True, text=True, timeout=15)
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return result, calls

    def test_wrapper_passes_context_and_semantic_suppression(self):
        result, calls = self.wrapper('''import os,sys,subprocess,json,time
helper=os.environ['WATCHSMITH_PROGRESS_HELPER']
c=json.loads(subprocess.check_output([sys.executable,helper,'claim']))
subprocess.check_call([sys.executable,helper,'finish','--token',c['token'],'--outcome','accepted'])
time.sleep(.6)
''', threshold='.4')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:2], ['activity', 'end-stream'])
        payload = json.loads(calls[0][-1])
        self.assertEqual(payload['auto_dismiss_minutes'], 0)
        self.assertEqual(payload['percentage'], 0)
        self.assertEqual(payload['type'], 'progress')

    def test_wrapper_fallback_and_exit_code(self):
        result, calls = self.wrapper('import time; time.sleep(.5); raise SystemExit(7)')
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual([c[:2] for c in calls], [['activity', 'stream'], ['activity', 'stream'], ['activity', 'end-stream']])
        self.assertEqual(calls[1][2], calls[2][2])
        payload = json.loads(calls[2][-1])
        self.assertEqual(payload['auto_dismiss_minutes'], 0)
        self.assertEqual(payload['type'], 'timer')
        self.assertFalse(payload['is_running'])
        self.assertIn('정상 종료되지', payload['subtitle'])
        self.assertNotIn(str(ROOT), json.dumps(calls))

    def test_unsupported_cli_pushes_once(self):
        result, calls = self.wrapper('import time; time.sleep(.5)', stream=False)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(sum(c[0] == 'push' for c in calls), 1)

    def test_invalid_threshold_does_not_start_child(self):
        result, calls = self.wrapper('raise SystemExit(9)', threshold='nan')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [])

    def test_short_command_has_no_notification(self):
        result, calls = self.wrapper('pass', threshold='10')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(calls, [])

    def test_corrupt_context_preserves_command_exit(self):
        result, calls = self.wrapper("import os,time; open(os.environ['WATCHSMITH_PROGRESS_CONTEXT'],'w').write('broken'); time.sleep(.5); raise SystemExit(7)")
        self.assertEqual(result.returncode, 7)
        self.assertEqual(calls, [])
        self.assertIn('command continues', result.stderr)


class ActivityTypeTests(unittest.TestCase):
    setUp = ProgressTests.setUp
    def test_types_survive_expired_claim_fallback_and_cleanup(self):
        examples = [
            {'type': 'progress', 'percentage': 37},
            {'type': 'segmented_progress', 'current_step': 2, 'number_of_steps': 4},
            {'type': 'timer', 'counts_down': False},
            {'type': 'alert', 'message': '검토 중'},
            {'type': 'stats', 'metrics': [{'label': '통과', 'value': 8}]},
            {'type': 'metrics', 'metrics': [{'label': '사용량', 'value': 40, 'unit': '%'}]},
        ]
        original = self.path.read_text()
        for example in examples:
            with self.subTest(kind=example['type']):
                self.path.write_text(original)
                first = P.claim(self.path, now=100, content_state=example)
                with patch.object(P, 'invoke', return_value=subprocess.CompletedProcess([], 0)) as call:
                    P.fallback(self.path, 'cli', {}, now=200)
                    payload = json.loads(call.call_args.args[1][-1])
                    self.assertEqual(payload['type'], example['type'])
                    P.close_run(self.path, 'cli', {}, 0)
                    payload = json.loads(call.call_args.args[1][-1])
                    self.assertEqual(payload['type'], example['type'])
                    self.assertEqual(payload['auto_dismiss_minutes'], 0)
                self.assertFalse(P.finish(self.path, first['token'], 'accepted'))

    def test_fallback_first_locks_timer_and_late_claim_inherits(self):
        data = json.loads(self.path.read_text())
        data.update(schema_version=2, started_at=100)
        self.path.write_text(json.dumps(data))
        with patch.object(P, 'invoke', return_value=subprocess.CompletedProcess([], 0)):
            P.fallback(self.path, 'cli', {}, now=200)
        result = P.claim(self.path, content_state={'type': 'segmented_progress', 'current_step': 1, 'number_of_steps': 3})
        self.assertTrue(result['type_locked'])
        self.assertEqual(result['content_state_type'], 'timer')
        self.assertIn('timer_start_at', result['content_state'])

    def test_type_lock_survives_failure_and_updates_same_type(self):
        first = P.claim(self.path, content_state={'type': 'progress', 'percentage': 25})
        P.finish(self.path, first['token'], 'failed')
        second = P.claim(self.path, content_state={'type': 'alert', 'message': 'Waiting'})
        self.assertEqual(second['content_state']['percentage'], 25)
        self.assertTrue(second['type_locked'])
        P.finish(self.path, second['token'], 'accepted')
        third = P.claim(self.path, content_state={'type': 'progress', 'percentage': 50})
        self.assertEqual(third['content_state']['percentage'], 50)
        P.ended(self.path)
        self.assertEqual(P.claim(self.path)['action'], 'skip')

    def test_invalid_content_does_not_change_state(self):
        before = self.path.read_bytes()
        for bad in ({'type': 'bogus'}, {'type': 'progress', 'percentage': float('nan')},
                    {'type': 'segmented_progress', 'current_step': 5, 'number_of_steps': 2},
                    {'type': 'stats', 'metrics': []}, {'type': 'timer', 'counts_down': True},
                    {'type': 'progress', 'percentage': 20, 'action': 'external'}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                P.claim(self.path, content_state=bad)
        self.assertEqual(before, self.path.read_bytes())

    def test_concurrent_different_types_select_only_one(self):
        env = dict(os.environ, WATCHSMITH_PROGRESS_CONTEXT=str(self.path))
        requested = [{'type': 'progress', 'percentage': 12}, {'type': 'timer'}]
        children = [subprocess.Popen([sys.executable, str(ROOT / 'bin/watchsmith_progress.py'),
                    'claim', '--content-state', json.dumps(item)], env=env, stdout=subprocess.PIPE, text=True)
                    for item in requested]
        results = [json.loads(p.communicate(timeout=10)[0]) for p in children]
        self.assertEqual(sorted(r['action'] for r in results), ['send', 'wait'])
        chosen = next(r for r in results if r['action'] == 'send')
        self.assertEqual(json.loads(self.path.read_text())['content_state']['type'], chosen['content_state_type'])

    def test_timer_handover_keeps_original_start(self):
        first = P.claim(self.path, content_state={'type': 'timer'})
        P.finish(self.path, first['token'], 'accepted')
        second = P.claim(self.path, content_state={'type': 'timer', 'timer_start_at': '2026-01-01T00:00:00Z'})
        self.assertEqual(first['content_state']['timer_start_at'], second['content_state']['timer_start_at'])
