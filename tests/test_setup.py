import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from test_notifications import ROOT, module

S = module('watchsmith_setup')


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='setup path ')
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'codex home'
        self.home.mkdir()
        self.env = dict(os.environ, CODEX_HOME=str(self.home))

    def install(self):
        subprocess.run(['zsh', str(ROOT / 'install.sh')], env=self.env, capture_output=True, check=True)

    def test_doctor_is_read_only_and_never_echoes_config_secrets(self):
        self.install()
        config = self.home / 'config.toml'
        config.write_text(config.read_text() + '\n[secret_fixture]\napi_key="PRIVATE_TEST_VALUE"\n')
        before = {str(p): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        with patch.object(S, 'key_present', return_value=True), patch.object(S.platform, 'system', return_value='Darwin'):
            rows = S.diagnose(self.home)
        self.assertNotIn('PRIVATE_TEST_VALUE', json.dumps(rows))
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.home.rglob('*') if p.is_file()})
        self.assertEqual(next(r for r in rows if r['check'] == 'Completion hook')['status'], 'ok')

    def test_modified_installed_file_is_reported(self):
        self.install()
        (self.home / 'bin/codex-watch').write_text('modified')
        with patch.object(S, 'key_present', return_value=False):
            rows = S.diagnose(self.home)
        self.assertEqual(next(r for r in rows if r['check'] == 'Installed files')['status'], 'error')

    def test_path_setup_is_quoted_idempotent_and_backed_up(self):
        shell = Path(self.tmp.name) / '.zshrc'
        shell.write_text('# personal settings\n')
        self.assertTrue(S.configure_path(self.home, shell))
        after = shell.read_bytes()
        self.assertFalse(S.configure_path(self.home, shell))
        self.assertEqual(shell.read_bytes(), after)
        backups = list((self.home / 'watchsmith/setup-backups').iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), '# personal settings\n')
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        check = subprocess.run(['zsh', '-c', 'source "$1"; print -r -- "$PATH"', 'fixture', str(shell)], capture_output=True, text=True)
        self.assertTrue(check.stdout.startswith(str(self.home / 'bin') + ':'))

    def test_path_symlink_not_replaced(self):
        shell = Path(self.tmp.name) / '.zshrc'
        target = Path(self.tmp.name) / 'shared'
        target.write_text('personal')
        shell.symlink_to(target)
        with self.assertRaises(ValueError):
            S.configure_path(self.home, shell)
        self.assertEqual(target.read_text(), 'personal')

    def test_setup_refuses_noninteractive_input(self):
        with patch.object(S.sys.stdin, 'isatty', return_value=False):
            self.assertEqual(S.setup(self.home), 2)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_source_install_can_be_declined_without_changes(self):
        with patch.object(S.sys.stdin, 'isatty', return_value=True), patch.object(S.platform, 'system', return_value='Darwin'), patch.object(S.shutil, 'which', return_value='/fake'), patch.object(S, 'confirm', return_value=False), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(S.setup(self.home, ROOT), 1)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_source_setup_reuses_key_and_skips_optional_changes(self):
        replies = iter([True, False, False])  # apply, PATH, test notification
        with patch.object(S.sys.stdin, 'isatty', return_value=True), patch.object(S.platform, 'system', return_value='Darwin'), patch.object(S.shutil, 'which', return_value='/fake'), patch.object(S, 'key_present', return_value=True), patch.object(S, 'confirm', side_effect=lambda _: next(replies)), patch.object(S, 'diagnose', return_value=[]), patch.dict(os.environ, os.environ.copy()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(S.setup(self.home, ROOT), 0)
        self.assertTrue((self.home / 'bin/watchsmith_setup.py').exists())
        self.assertTrue((self.home / 'watchsmith/installation.json').exists())

    def test_unsafe_manifest_path_is_reported_without_reading_it(self):
        (self.home / 'watchsmith').mkdir()
        (self.home / 'watchsmith/installation.json').write_text(json.dumps({'installed_hashes': {'../../private': 'x'}}))
        with patch.object(S, 'key_present', return_value=False):
            rows = S.diagnose(self.home)
        self.assertEqual(next(r for r in rows if r['check'] == 'Installed files')['status'], 'error')

    def test_installed_doctor_creates_no_bytecode_or_state(self):
        self.install()
        fake = Path(self.tmp.name) / 'fake-bin'
        fake.mkdir()
        security = fake / 'security'
        security.write_text('#!/bin/sh\nexit 0\n')
        security.chmod(0o755)
        before = {str(p): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        env = dict(self.env, PATH=str(fake) + os.pathsep + self.env['PATH'])
        result = subprocess.run([str(self.home / 'bin/watchsmith'), 'doctor', '--json'], env=env, capture_output=True, text=True)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        self.assertIsInstance(json.loads(result.stdout), list)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.home.rglob('*') if p.is_file()})

    def test_missing_npm_stops_without_installing(self):
        def which(command):
            return '/bin/zsh' if command == 'zsh' else None
        with patch.object(S.sys.stdin, 'isatty', return_value=True), patch.object(S.platform, 'system', return_value='Darwin'), patch.object(S.shutil, 'which', side_effect=which), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(S.setup(self.home, ROOT), 1)
        self.assertEqual(list(self.home.iterdir()), [])
