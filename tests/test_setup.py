import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
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
        fake_bin = Path(self.tmp.name) / 'old python bin'
        fake_bin.mkdir()
        old_python = fake_bin / 'python3'
        old_python.write_text('#!/bin/sh\nexit 42\n')
        old_python.chmod(0o755)
        path_patch = patch.dict(os.environ, {'PATH': str(fake_bin) + os.pathsep + os.environ['PATH']})
        path_patch.start()
        self.addCleanup(path_patch.stop)
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


class LauncherTests(unittest.TestCase):
    def test_skips_incompatible_default_and_preserves_arguments_and_exit_code(self):
        with tempfile.TemporaryDirectory(prefix='launcher path ') as tmp:
            root = Path(tmp)
            launcher = root / 'watchsmith'
            launcher.write_bytes((ROOT / 'bin/watchsmith').read_bytes())
            launcher.chmod(0o755)
            (root / 'watchsmith_update.py').write_text('import json,sys; print(json.dumps(sys.argv[1:])); sys.exit(7)')
            old = root / 'python3'
            old.write_text('#!/bin/sh\nexit 1\n')
            old.chmod(0o755)
            compatible = root / 'python3.11'
            compatible.symlink_to(sys.executable)
            result = subprocess.run([str(launcher), 'doctor', 'argument with spaces'], env=dict(os.environ, PATH=tmp), capture_output=True, text=True)
            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertEqual(json.loads(result.stdout), ['doctor', 'argument with spaces'])

    def test_no_compatible_python_has_clear_error(self):
        # Isolate discovery locations to model a machine with only old Python.
        with tempfile.TemporaryDirectory(prefix='no python ') as tmp:
            source = (ROOT / 'bin/watchsmith').read_text()
            start = source.index('watchsmith_pythons=(')
            end = source.index('\n)', start) + 2
            source = source[:start] + 'watchsmith_pythons=(python3)' + source[end:]
            launcher = Path(tmp) / 'watchsmith'
            launcher.write_text(source)
            launcher.chmod(0o755)
            old = Path(tmp) / 'python3'
            old.write_text('#!/bin/sh\nexit 1\n')
            old.chmod(0o755)
            result = subprocess.run([str(launcher), 'doctor'], env=dict(os.environ, PATH=tmp), capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('Python 3.11+', result.stderr)
            self.assertNotIn('Traceback', result.stderr)
            self.assertEqual(result.stdout, '')
