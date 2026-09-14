import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_notifications import ROOT, module

M = module('watchsmith_install')


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='watchsmith migration ')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'codex home'
        self.home.mkdir()
        self.env = dict(os.environ, CODEX_HOME=str(self.home))

    def run_installer(self, *flags, expected=0, script='install.sh'):
        p = subprocess.run(['zsh', str(ROOT / script), *flags], env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, expected, p.stderr)
        return p

    def test_check_is_read_only_and_noop_reinstall(self):
        self.run_installer('--check')
        self.assertEqual(list(self.home.iterdir()), [])
        self.run_installer()
        manifest = (self.home / 'watchsmith/installation.json').read_bytes()
        self.run_installer()
        self.assertEqual(manifest, (self.home / 'watchsmith/installation.json').read_bytes())
        self.assertEqual(len(list((self.home / 'watchsmith/transactions').iterdir())), 1)

    def test_rollback_restores_original_files(self):
        (self.home / 'config.toml').write_text('# original\nnotify = ["existing"]\n')
        (self.home / 'AGENTS.md').write_text('Personal instructions\n')
        before = {p: M.image(self.home / p) for p in M.TRACKED}
        self.run_installer()
        self.run_installer('--rollback', 'latest', '--quiesced')
        self.assertEqual(before, {p: M.image(self.home / p) for p in M.TRACKED})

    def test_modified_helper_is_not_overwritten(self):
        (self.home / 'bin').mkdir()
        (self.home / 'bin/activitysmith_notify.py').write_text('user customization\n')
        self.run_installer('--check', expected=1)
        self.assertFalse((self.home / 'watchsmith').exists())
        self.assertFalse((self.home / 'config.toml').exists())

    def test_rollback_conflict_preserves_edits(self):
        self.run_installer()
        (self.home / 'config.toml').write_text('notify = ["new-personal-choice"]\n')
        self.run_installer('--rollback', 'latest', '--quiesced', expected=1)
        self.assertIn('new-personal-choice', (self.home / 'config.toml').read_text())
        self.assertTrue((self.home / 'bin/watchsmith_delivery.py').exists())

    def test_failure_during_copy_is_rolled_back(self):
        before, after, _ = M.prepare(self.home)
        def failing_writer(path, item):
            if path.name == 'codex-watch':
                raise OSError('injected copy failure')
            M.put(path, item)
        with self.assertRaises(OSError):
            M.transact(self.home, before, after, 'install', writer=failing_writer)
        self.assertEqual(before, {p: M.image(self.home / p) for p in M.TRACKED})

    def test_interrupted_install_has_explicit_recovery(self):
        before, after, _ = M.prepare(self.home)
        def crash(path, item):
            M.put(path, item)
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            M.transact(self.home, before, after, 'install', writer=crash)
        self.run_installer('--check', expected=1)
        self.run_installer('--rollback', 'latest', '--quiesced')
        self.assertEqual(before, {p: M.image(self.home / p) for p in M.TRACKED})

    def test_previous_chain_cycle_is_rejected(self):
        argv = ['python3', str(self.home / 'bin/watchsmith_notify_dispatcher.py')]
        (self.home / 'config.toml').write_text('notify = ' + json.dumps(argv))
        (self.home / 'watchsmith').mkdir()
        (self.home / 'watchsmith/previous_notify.json').write_text(json.dumps(argv))
        self.run_installer('--check', expected=1)
        self.assertFalse((self.home / 'bin').exists())

    def test_legacy_original_helper_is_restored_on_uninstall(self):
        # Use the exact previous tracked runtime, recognized by its known hash.
        old = (ROOT / 'tests/fixtures/legacy_activitysmith_notify.py').read_bytes()
        (self.home / 'bin').mkdir()
        helper = self.home / 'bin/activitysmith_notify.py'
        helper.write_bytes(old)
        helper.chmod(0o751)
        nested = ['python3', str(helper)]
        argv = ['/example/SkyComputerUseClient', 'turn-ended', '--previous-notify', json.dumps(nested)]
        (self.home / 'config.toml').write_text('notify = ' + json.dumps(argv))
        self.run_installer('--check')
        self.run_installer('--upgrade', expected=1)
        self.run_installer('--upgrade', '--quiesced')
        self.run_installer('--quiesced', script='uninstall.sh')
        self.assertEqual(helper.read_bytes(), old)
        self.assertEqual(helper.stat().st_mode & 0o777, 0o751)
        import tomllib
        self.assertEqual(tomllib.loads((self.home / 'config.toml').read_text())['notify'], argv)
        self.assertFalse((self.home / 'bin/watchsmith_delivery.py').exists())

    def test_modified_saved_notifier_is_not_overwritten_on_removal(self):
        self.run_installer()
        saved = self.home / 'watchsmith/previous_notify.json'
        saved.write_text('["user-updated-notifier"]')
        self.run_installer('--quiesced', script='uninstall.sh', expected=1)
        self.assertEqual(saved.read_text(), '["user-updated-notifier"]')
        self.assertTrue((self.home / 'bin/watchsmith_delivery.py').exists())

    def test_check_cannot_activate_rollback(self):
        self.run_installer()
        cfg = (self.home / 'config.toml').read_bytes()
        self.run_installer('--check', '--rollback', 'latest', '--quiesced', expected=2)
        self.assertEqual(cfg, (self.home / 'config.toml').read_bytes())
