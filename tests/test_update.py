import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from test_notifications import ROOT, module

U = module('watchsmith_update')


class UpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix='release test ')
        cls.addClassCleanup(cls.workspace.cleanup)
        repo = Path(cls.workspace.name) / 'source'
        repo.mkdir()
        for name in ('bin', 'config', 'docs', 'scripts'):
            shutil.copytree(ROOT / name, repo / name, ignore=shutil.ignore_patterns('__pycache__', 'VERIFICATION.md', 'MIGRATION_PLAN.md'))
        for name in ('install.sh', 'uninstall.sh', 'setup.sh', 'README.md', 'README.ko.md', 'LICENSE', 'CONTRIBUTING.md'):
            shutil.copy(ROOT / name, repo / name)
        (repo / 'VERSION').write_text('0.2.0\n')
        with (repo / 'bin/watchsmith_update.py').open('a') as file:
            file.write('\n# Release fixture change for self-update/rollback verification.\n')
        def git(*args):
            subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True)
        git('init')
        git('add', '.')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'Release fixture')
        git('tag', 'v0.2.0')
        cls.output = Path(cls.workspace.name) / 'dist'
        subprocess.run([sys.executable, str(ROOT / 'scripts/build-release.py'), '--ref', 'v0.2.0', '--output', str(cls.output)], cwd=repo, check=True, capture_output=True)
        cls.blob = (cls.output / 'codex-watchsmith-v0.2.0.tar.gz').read_bytes()
        cls.checksum = (cls.output / 'SHA256SUMS').read_text()
        cls.release = {'tag_name': 'v0.2.0', 'draft': False, 'prerelease': False, 'assets': [
            {'name': n, 'browser_download_url': f'https://github.com/{U.REPO}/releases/download/v0.2.0/{n}'}
            for n in ('codex-watchsmith-v0.2.0.tar.gz', 'SHA256SUMS')]}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'installed home'
        self.home.mkdir()

    def test_release_package_checks_and_inventory(self):
        root, digest = U.unpack(self.blob, self.checksum, 'v0.2.0', self.home)
        self.assertEqual(digest, hashlib.sha256(self.blob).hexdigest())
        self.assertTrue((root / 'bin/watchsmith').exists())
        self.assertFalse((root / 'docs/VERIFICATION.md').exists())
        self.assertFalse((root / 'tests').exists())

    def test_corrupt_download_never_extracts(self):
        with self.assertRaises(ValueError):
            U.unpack(self.blob + b'corrupt', self.checksum, 'v0.2.0', self.home)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_unsafe_archives_rejected(self):
        for name, kind in (('../escape', tarfile.REGTYPE), ('/escape', tarfile.REGTYPE),
                           ('link', tarfile.SYMTYPE), ('hard', tarfile.LNKTYPE)):
            out = io.BytesIO()
            with tarfile.open(fileobj=out, mode='w:gz') as tar:
                item = tarfile.TarInfo(name); item.type = kind
                tar.addfile(item)
            blob = out.getvalue()
            checksum = hashlib.sha256(blob).hexdigest() + '  codex-watchsmith-v0.2.0.tar.gz\n'
            with self.subTest(name=name), self.assertRaises(ValueError):
                U.unpack(blob, checksum, 'v0.2.0', self.home)

    def test_release_version_mismatch_rejected(self):
        wrong = self.checksum.replace('v0.2.0', 'v0.3.0')
        with self.assertRaises(ValueError):
            U.unpack(self.blob, wrong, 'v0.3.0', self.home)

    def test_no_missing_assets_or_foreign_downloads(self):
        with self.assertRaises(ValueError):
            U.asset_url(dict(self.release, assets=[]), 'SHA256SUMS')
        malicious = dict(self.release, assets=[{'name': 'SHA256SUMS', 'browser_download_url': 'https://example.com/file'}])
        with self.assertRaises(ValueError):
            U.asset_url(malicious, 'SHA256SUMS')

    def test_stable_version_order(self):
        self.assertLess(U.version('v0.1.9'), U.version('v0.2.0'))
        self.assertLess(U.version('0.2.0-dev'), U.version('0.2.0'))
        for tag in ('main', '../x', 'v0.2.0-beta'):
            with self.assertRaises(ValueError):
                U.version(tag)

    def call(self, *args):
        with patch.object(U, 'home', return_value=self.home), patch.object(U, 'release', return_value=self.release), patch.object(sys, 'argv', ['watchsmith', *args]), contextlib.redirect_stdout(io.StringIO()):
            return U.main()

    def test_check_has_no_local_side_effects(self):
        with patch.object(U, 'download') as network:
            self.assertEqual(self.call('update', '--check'), 0)
            network.assert_not_called()
        self.assertEqual(list(self.home.iterdir()), [])

    def test_update_requires_explicit_quiescence(self):
        with patch.object(U, 'download') as network:
            self.assertEqual(self.call('update'), 1)
            network.assert_not_called()
        self.assertEqual(list(self.home.iterdir()), [])

    def test_install_update_and_rollback_without_git_at_runtime(self):
        env = dict(os.environ, CODEX_HOME=str(self.home))
        subprocess.run(['zsh', str(ROOT / 'install.sh')], env=env, capture_output=True, check=True)
        manifest_path = self.home / 'watchsmith/installation.json'
        old_manifest = json.loads(manifest_path.read_text())
        old_manifest['release']['version'] = '0.1.0'
        manifest_path.write_text(json.dumps(old_manifest))
        before = manifest_path.read_bytes()
        runtime_before = (self.home / 'bin/watchsmith_update.py').read_bytes()
        # Reproduce a shell whose default Python cannot import tomllib.
        fake_bin = Path(self.tmp.name) / 'old python bin'
        fake_bin.mkdir()
        marker = fake_bin / 'unexpected-python-call'
        old_python = fake_bin / 'python3'
        old_python.write_text('#!/bin/sh\necho called > "' + str(marker) + '"\nexit 42\n')
        old_python.chmod(0o755)
        env['PATH'] = str(fake_bin) + os.pathsep + env['PATH']
        path_patch = patch.dict(os.environ, {'PATH': env['PATH']})
        path_patch.start()
        self.addCleanup(path_patch.stop)
        with patch.object(U, 'download', side_effect=lambda url, limit: self.checksum.encode() if url.endswith('SHA256SUMS') else self.blob):
            self.assertEqual(self.call('update', '--quiesced'), 0)
        self.assertNotEqual((self.home / 'bin/watchsmith_update.py').read_bytes(), runtime_before)
        metadata = U.installed(self.home)
        self.assertEqual(metadata['version'], '0.2.0')
        self.assertEqual(metadata['package_sha256'], hashlib.sha256(self.blob).hexdigest())
        with patch.object(U, 'download') as network:
            self.assertEqual(self.call('update', '--quiesced'), 0)
            network.assert_not_called()
        self.assertFalse(marker.exists(), 'installation reselected PATH python3')
        result = subprocess.run([str(self.home / 'bin/watchsmith'), 'rollback', '--quiesced'], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.home / 'watchsmith/installation.json').read_bytes(), before)
        self.assertEqual((self.home / 'bin/watchsmith_update.py').read_bytes(), runtime_before)

    def test_failed_preflight_preserves_existing_installation(self):
        env = dict(os.environ, CODEX_HOME=str(self.home))
        subprocess.run([sys.executable, str(ROOT / 'bin/watchsmith_install.py'), 'install'], env=env, capture_output=True, check=True)
        manifest_path = self.home / 'watchsmith/installation.json'
        record = json.loads(manifest_path.read_text())
        record['release']['version'] = '0.1.0'
        manifest_path.write_text(json.dumps(record))
        (self.home / 'bin/codex-watch').write_text('user modification')
        (self.home / 'watchsmith/update.lock').touch()
        before = {str(p): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        with patch.object(U, 'download', side_effect=lambda url, limit: self.checksum.encode() if url.endswith('SHA256SUMS') else self.blob):
            self.assertEqual(self.call('update', '--quiesced'), 1)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.home.rglob('*') if p.is_file()})

    def test_prerelease_api_response_rejected(self):
        with patch.object(U, 'download', return_value=json.dumps(dict(self.release, prerelease=True)).encode()):
            with self.assertRaises(ValueError):
                U.release()

    def test_expansion_limit_is_checked_before_extraction(self):
        with patch.object(U, 'MAX_EXPANDED', 1), self.assertRaises(ValueError):
            U.unpack(self.blob, self.checksum, 'v0.2.0', self.home)
        self.assertFalse((self.home / 'source').exists())

    def test_concurrent_update_is_rejected_before_download(self):
        import fcntl
        (self.home / 'watchsmith').mkdir()
        with (self.home / 'watchsmith/update.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(U, 'download') as network:
                self.assertEqual(self.call('update', '--quiesced'), 1)
                network.assert_not_called()

    def test_generated_bootstrap_verifies_before_launching_setup(self):
        namespace = {'__name__': 'bootstrap_fixture'}
        exec((self.output / 'watchsmith-bootstrap.py').read_text(), namespace)
        namespace['release'] = lambda tag: self.release
        namespace['download'] = lambda url, limit: self.checksum.encode() if url.endswith('SHA256SUMS') else self.blob
        def launch(command, env):
            self.assertEqual(command[0], sys.executable)
            self.assertTrue(Path(command[1]).is_file())
            self.assertEqual(Path(command[1]).name, 'watchsmith_setup.py')
            self.assertEqual(command[2:], ['setup'])
            self.assertEqual(env['WATCHSMITH_PACKAGE_SHA256'], hashlib.sha256(self.blob).hexdigest())
            return 0
        with patch.object(sys, 'argv', ['bootstrap']), patch.object(sys.stdin, 'isatty', return_value=True), patch.object(subprocess, 'call', side_effect=launch) as call:
            self.assertEqual(namespace['bootstrap_main'](), 0)
            call.assert_called_once()

    def test_bootstrap_rejects_bad_package_before_execution(self):
        namespace = {'__name__': 'bootstrap_fixture'}
        exec((self.output / 'watchsmith-bootstrap.py').read_text(), namespace)
        namespace['release'] = lambda tag: self.release
        namespace['download'] = lambda url, limit: self.checksum.encode() if url.endswith('SHA256SUMS') else b'corrupt'
        with patch.object(sys, 'argv', ['bootstrap']), patch.object(sys.stdin, 'isatty', return_value=True), patch.object(subprocess, 'call') as call:
            self.assertEqual(namespace['bootstrap_main'](), 1)
            call.assert_not_called()

    def test_native_https_follows_only_validated_redirects(self):
        responses = iter([(302, 'https://release-assets.githubusercontent.com/file', b''), (200, None, b'package')])
        def curl(args, **kwargs):
            code, location, data = next(responses)
            Path(args[args.index('--output') + 1]).write_bytes(data)
            Path(args[args.index('--dump-header') + 1]).write_text('Location: ' + location + '\n' if location else '')
            return subprocess.CompletedProcess(args, 0, str(code), '')
        with patch.object(U.subprocess, 'run', side_effect=curl) as call:
            self.assertEqual(U.curl_download('https://github.com/example', 100), b'package')
            self.assertEqual(call.call_count, 2)
            self.assertNotIn('--insecure', call.call_args.args[0])

    def test_native_https_rejects_foreign_redirect_before_following(self):
        def curl(args, **kwargs):
            Path(args[args.index('--output') + 1]).write_bytes(b'')
            Path(args[args.index('--dump-header') + 1]).write_text('Location: https://example.com/private\n')
            return subprocess.CompletedProcess(args, 0, '302', '')
        with patch.object(U.subprocess, 'run', side_effect=curl) as call, self.assertRaises(ValueError):
            U.curl_download('https://github.com/example', 100)
        self.assertEqual(call.call_count, 1)
