import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bin'))


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'bin' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='watchsmith space ')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'custom codex'
        self.home.mkdir()
        self.cfg = self.home / 'config.toml'
        self.env = dict(os.environ, CODEX_HOME=str(self.home))

    def run_script(self, name, success=True):
        result = subprocess.run(['zsh', str(ROOT / name), '--quiesced'], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stderr)

    def test_multiline_notify_roundtrip_and_dispatch(self):
        recorder = self.home / 'Computer Use recorder.py'
        output = self.home / 'received.json'
        recorder.write_text('import json,sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))\n')
        old = [sys.executable, str(recorder), str(output), 'turn-ended', 'a b', '', '"quoted"', '$HOME', '한글', '--previous-notify', json.dumps(['python3', '/a path/notifier.py'])]
        tail = '\n[profiles.test]\nnotify = ["leave nested alone"]\n'
        original = '# keep comment\n"notify" = [\n' + ''.join(json.dumps(x, ensure_ascii=False) + ', # argument\n' for x in old) + '] # closing\n' + tail
        self.cfg.write_text(original)
        self.run_script('install.sh')
        installed = self.cfg.read_text()
        self.assertTrue((self.home / 'bin' / 'watchsmith_result.py').exists())
        self.assertTrue(installed.endswith(tail))
        self.assertTrue(installed.startswith('# keep comment\n'))
        previous = self.home / 'watchsmith' / 'previous_notify.json'
        self.assertEqual(json.loads(previous.read_text()), old)
        backups = list((self.home / 'watchsmith/transactions').glob('*/journal.json'))
        import base64
        saved_config = json.loads(backups[0].read_text())['before']['config.toml']['data']
        self.assertEqual(base64.b64decode(saved_config).decode(), original)
        self.run_script('install.sh')
        self.assertEqual(self.cfg.read_text(), installed)
        self.assertEqual(json.loads(previous.read_text()), old)
        self.assertEqual(len(list((self.home / 'watchsmith/transactions').glob('*/journal.json'))), 1)
        # Exercise the installed dispatcher with CODEX_HOME absent, as in a GUI launch.
        shim = self.home / 'test tools'
        shim.mkdir()
        for name in ('activitysmith', 'security'):
            tool = shim / name
            tool.write_text('#!/bin/sh\nexit 1\n')
            tool.chmod(0o755)
        env = dict(os.environ)
        env.pop('CODEX_HOME', None)
        env.pop('ACTIVITYSMITH_API_KEY', None)
        env['PATH'] = str(shim) + os.pathsep + env['PATH']
        payload = '{ "type": "agent-turn-complete", "text": "a b\\n한글" }'
        subprocess.run(tomllib.loads(installed)['notify'] + [payload], env=env, check=True)
        deadline = time.monotonic() + 5
        while not output.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertEqual(json.loads(output.read_text()), old[3:] + [payload])
        self.run_script('uninstall.sh')
        self.assertEqual(tomllib.loads(self.cfg.read_text())['notify'], old)
        self.assertFalse((self.home / 'bin' / 'watchsmith_result.py').exists())
        self.assertTrue(self.cfg.read_text().endswith(tail))
        self.run_script('uninstall.sh')

    def test_invalid_config_is_untouched(self):
        for original in ['notify = [\n', 'notify = 3\n', 'notify = ["ok", 3]\n', 'notify = []\nnotify = []\n']:
            with self.subTest(original=original):
                self.cfg.write_text(original)
                self.run_script('install.sh', success=False)
                self.assertEqual(self.cfg.read_text(), original)
                self.assertFalse((self.home / 'bin').exists())
                self.assertFalse((self.home / 'watchsmith').exists())

    def test_no_notify_clears_stale_state(self):
        state = self.home / 'watchsmith'
        state.mkdir()
        (state / 'previous_notify.json').write_text('["stale"]')
        self.cfg.write_text('[profile]\nnotify = ["nested"]\n')
        self.run_script('install.sh')
        self.assertIsNone(json.loads((state / 'previous_notify.json').read_text()))
        self.run_script('uninstall.sh')
        self.assertNotIn('notify', tomllib.loads(self.cfg.read_text()))

    def test_missing_saved_state_stops_uninstall(self):
        self.run_script('install.sh')
        before = self.cfg.read_text()
        (self.home / 'watchsmith' / 'previous_notify.json').unlink()
        self.run_script('uninstall.sh', success=False)
        self.assertEqual(before, self.cfg.read_text())
        self.assertTrue((self.home / 'bin' / 'watchsmith_notify_dispatcher.py').exists())
        self.run_script('install.sh', success=False)

    def test_user_replacement_is_preserved(self):
        self.run_script('install.sh')
        self.cfg.write_text('notify = ["replacement"]\n')
        self.run_script('uninstall.sh')
        self.assertEqual(tomllib.loads(self.cfg.read_text())['notify'], ['replacement'])

    def test_multiline_string_containing_fake_notify(self):
        text = 'description = """\nnotify = ["fake"]\n"""\nnotify = ["real"]\n'
        self.cfg.write_text(text)
        self.run_script('install.sh')
        self.assertEqual(json.loads((self.home / 'watchsmith' / 'previous_notify.json').read_text()), ['real'])
        self.run_script('uninstall.sh')
        self.assertEqual(tomllib.loads(text), tomllib.loads(self.cfg.read_text()))


class NotificationTests(unittest.TestCase):
    def test_completion_is_generic(self):
        notifier = module('activitysmith_notify')
        payload = json.dumps({'type': 'agent-turn-complete', 'prompt': 'PRIVATE', 'last-assistant-message': 'SECRET'})
        with patch.object(sys, 'argv', ['notify', payload]), patch.object(notifier, 'get_key', return_value='test-key'), patch.object(notifier.shutil, 'which', return_value='/fake/activitysmith'), patch.object(notifier.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'Success: true')) as launch:
            self.assertEqual(notifier.main(), 0)
            args = launch.call_args.args[0]
            self.assertEqual(args, ['/fake/activitysmith', 'push', '--title', 'Codex 작업 완료', '--message', '요청한 에이전트 작업이 완료되었습니다.'])
            self.assertNotIn('PRIVATE', str(launch.call_args))
            self.assertNotIn('SECRET', str(launch.call_args))

    def test_ignored_events(self):
        notifier = module('activitysmith_notify')
        for payload in ['bad json', 'null', '[]', '123', '{}', '{"type":"other"}']:
            with patch.object(sys, 'argv', ['notify', payload]), patch.object(notifier.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'Success: true')) as launch:
                self.assertEqual(notifier.main(), 0)
                launch.assert_not_called()

    def test_previous_failure_does_not_block_completion(self):
        dispatcher = module('watchsmith_notify_dispatcher')
        with tempfile.TemporaryDirectory() as directory:
            prev = Path(directory) / 'previous.json'
            prev.write_text('["/missing/notifier"]')
            with patch.object(dispatcher, 'PREV', prev), patch.object(sys, 'argv', ['dispatcher', '{}']), patch.object(dispatcher.subprocess, 'Popen', side_effect=[FileNotFoundError(), None]) as launch:
                self.assertEqual(dispatcher.main(), 0)
                self.assertEqual(launch.call_count, 2)
                self.assertEqual(launch.call_args.args[0][-1], '{}')


if __name__ == '__main__':
    unittest.main()
