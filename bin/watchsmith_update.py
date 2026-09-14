#!/usr/bin/env python3
"""Explicit updates from official release assets; never execute an unverified archive."""
import argparse
import fcntl
import hashlib
import json
import os
import platform
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request

REPO = 'GrooshBene/codex-watchsmith'
MAX_PACKAGE = 32 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024


def version(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(-dev)?', value)
    if not match:
        raise ValueError('invalid version')
    return (*map(int, match.group(1, 2, 3)), not bool(match[4]))


def home():
    # Installed commands follow their own installation, including GUI environments.
    return Path(__file__).resolve().parent.parent


def installed(root):
    p = root / 'watchsmith/installation.json'
    return json.loads(p.read_text()).get('release', {}) if p.exists() else {}


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        host = parsed.hostname or ''
        if parsed.scheme != 'https' or parsed.username or parsed.password or not (
                host == 'github.com' or host == 'api.github.com'
                or host.endswith('.githubusercontent.com')):
            raise ValueError('unexpected download redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def curl_download(url, limit):
    """Use macOS curl's native trust store; validate each redirect before following."""
    for _ in range(6):
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname or ''
        if parsed.scheme != 'https' or parsed.username or parsed.password or not (
                host in ('github.com', 'api.github.com') or host.endswith('.githubusercontent.com')):
            raise ValueError('unexpected HTTPS download destination')
        with tempfile.TemporaryDirectory(prefix='watchsmith-https-') as directory:
            body = Path(directory) / 'body'
            headers = Path(directory) / 'headers'
            response = subprocess.run(['/usr/bin/curl', '--proto', '=https', '--silent', '--show-error',
                '--max-time', '30', '--max-filesize', str(limit), '--output', str(body),
                '--dump-header', str(headers), '--write-out', '%{http_code}',
                '--user-agent', 'codex-watchsmith-updater', url], capture_output=True, text=True, timeout=35)
            if response.returncode:
                raise ValueError('HTTPS download failed; check network and system certificate trust')
            code = int(response.stdout)
            if code in (301, 302, 303, 307, 308):
                locations = [line.split(':', 1)[1].strip() for line in headers.read_text().splitlines()
                             if line.lower().startswith('location:')]
                if len(locations) != 1:
                    raise ValueError('ambiguous download redirect')
                url = urllib.parse.urljoin(url, locations[0])
                continue
            if code != 200:
                raise ValueError('release server returned HTTP ' + str(code))
            with body.open('rb') as file:
                data = file.read(limit + 1)
            if len(data) > limit:
                raise ValueError('download exceeds size limit')
            return data
    raise ValueError('too many download redirects')


def download(url, limit):
    if platform.system() == 'Darwin':
        return curl_download(url, limit)
    request = urllib.request.Request(url, headers={'User-Agent': 'codex-watchsmith-updater',
                                                  'Accept': 'application/vnd.github+json'})
    with urllib.request.build_opener(SafeRedirect()).open(request, timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('download exceeds size limit')
    return data


def release(tag=None):
    if tag and (not re.fullmatch(r'v\d+\.\d+\.\d+', tag)):
        raise ValueError('choose a stable version such as v0.2.0')
    endpoint = 'tags/' + tag if tag else 'latest'
    data = json.loads(download(f'https://api.github.com/repos/{REPO}/releases/{endpoint}', 1024 * 1024))
    actual = data['tag_name']
    if not re.fullmatch(r'v\d+\.\d+\.\d+', actual) or data['draft'] or data['prerelease']:
        raise ValueError('release is not a published stable version')
    if tag and actual != tag:
        raise ValueError('release tag mismatch')
    return data


def asset_url(data, name):
    matches = [a for a in data['assets'] if a['name'] == name]
    if len(matches) != 1:
        raise ValueError('release has no updater package/checksum; use the documented one-time manual upgrade')
    expected = f'https://github.com/{REPO}/releases/download/{data["tag_name"]}/{name}'
    if matches[0]['browser_download_url'] != expected:
        raise ValueError('unexpected release asset URL')
    return expected


def unpack(blob, checksum, tag, destination):
    name = f'codex-watchsmith-{tag}.tar.gz'
    if not re.fullmatch(r'[0-9a-f]{64}  ' + re.escape(name) + r'\n?', checksum):
        raise ValueError('invalid checksum file')
    digest = hashlib.sha256(blob).hexdigest()
    if digest != checksum.split()[0]:
        raise ValueError('package checksum mismatch; nothing installed')
    archive = destination / 'package.tar.gz'
    archive.write_bytes(blob)
    files = set()
    with tarfile.open(archive, 'r:gz') as tar:
        total = 0
        members = []
        for member in tar:
            members.append(member)
            if len(members) > 256:
                raise ValueError('too many package files')
            path = PurePosixPath(member.name)
            if (not member.isfile() or path.is_absolute() or '..' in path.parts
                    or str(path) != member.name or member.name in files or '\\' in member.name):
                raise ValueError('unsafe archive member')
            files.add(member.name)
            total += member.size
            if total > MAX_EXPANDED:
                raise ValueError('expanded package exceeds size limit')
        for member in members:
            target = destination / 'source' / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(member).read())
            target.chmod(0o755 if member.name.startswith('bin/') or member.name.endswith('.sh') else 0o644)
    root = destination / 'source'
    metadata = json.loads((root / 'release.json').read_text())
    if (metadata.get('schema_version') != 1 or metadata.get('version') != tag[1:]
            or not re.fullmatch('[0-9a-f]{40}', metadata.get('commit', ''))
            or (root / 'VERSION').read_text().strip() != tag[1:]):
        raise ValueError('release metadata mismatch')
    expected = metadata['files']
    if set(expected) != files - {'release.json'}:
        raise ValueError('package file inventory mismatch')
    for name, file_hash in expected.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != file_hash:
            raise ValueError('package file digest mismatch')
    required = {'install.sh', 'bin/watchsmith_install.py', 'bin/watchsmith_config.py',
                'bin/watchsmith_update.py', 'bin/watchsmith', 'config/activitysmith-agents.md',
                'config/known-runtime-hashes.json'}
    if not required.issubset(files):
        raise ValueError('incomplete release package')
    return root, digest


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('setup', 'doctor'):
        from watchsmith_setup import main as setup_main
        return setup_main(sys.argv[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('version')
    sub.add_parser('setup', help='interactive connection and installation guidance')
    sub.add_parser('doctor', help='read-only local diagnostics')
    update = sub.add_parser('update')
    update.add_argument('--check', action='store_true')
    update.add_argument('--version', help='published stable tag, for example v0.2.0')
    update.add_argument('--quiesced', action='store_true', help='confirm affected jobs and clients have stopped')
    rollback = sub.add_parser('rollback')
    rollback.add_argument('--quiesced', action='store_true')
    rollback.add_argument('--transaction', default='latest')
    args = parser.parse_args()
    root = home()
    lock = None
    try:
        if args.command in ('update', 'rollback') and args.quiesced and not getattr(args, 'check', False):
            lock = (root / 'watchsmith/update.lock').open('a')
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        current = installed(root)
        if args.command == 'version':
            print(json.dumps(current or {'version': 'unknown (legacy installation)'}, indent=2))
            return 0
        if args.command == 'rollback':
            if not args.quiesced:
                raise ValueError('finish jobs and close affected clients, then use --quiesced')
            env = dict(os.environ, CODEX_HOME=str(root))
            return subprocess.call([sys.executable, str(root / 'bin/watchsmith_install.py'),
                                    'install', '--rollback', args.transaction, '--quiesced'], env=env)
        data = release(args.version)
        target = data['tag_name']
        newer = current.get('version') in (None, 'unknown') or version(target) > version(current['version'])
        print(json.dumps({'installed': current.get('version', 'unknown'), 'available': target,
                          'update_available': newer,
                          'release_notes': f'https://github.com/{REPO}/releases/tag/{target}'}, indent=2))
        if not newer:
            return 0
        package = f'codex-watchsmith-{target}.tar.gz'
        package_url = asset_url(data, package)
        checksum_url = asset_url(data, 'SHA256SUMS')
        if args.check:
            return 0
        if not args.quiesced:
            raise ValueError('finish jobs and close affected clients, then run update --quiesced; no files changed')
        blob = download(package_url, MAX_PACKAGE)
        checksum = download(checksum_url, 4096).decode('ascii')
        with tempfile.TemporaryDirectory(prefix='watchsmith-update-') as directory:
            source, digest = unpack(blob, checksum, target, Path(directory))
            env = dict(os.environ, CODEX_HOME=str(root), WATCHSMITH_PACKAGE_SHA256=digest)
            # Retain the launcher's compatible interpreter across installation.
            base = [sys.executable, str(source / 'bin/watchsmith_install.py'), 'install']
            subprocess.run(base + ['--check'], env=env, check=True)
            subprocess.run(base + ['--upgrade', '--quiesced'], env=env, check=True)
            manifest = json.loads((root / 'watchsmith/installation.json').read_text())
            if manifest.get('release', {}).get('package_sha256') != digest:
                raise ValueError('post-install metadata mismatch; use rollback before retrying')
            for name, expected in manifest['installed_hashes'].items():
                path = PurePosixPath(name)
                if path.is_absolute() or '..' in path.parts or path.parts[0] != 'bin':
                    raise ValueError('invalid installed inventory')
                if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
                    raise ValueError('post-install file mismatch; use rollback before retrying')
        print('Update applied. Restart Codex; recovery is available with watchsmith rollback --quiesced.')
        return 0
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, subprocess.SubprocessError) as error:
        # Network errors may include remote text. Do not print response bodies or URLs.
        print('[watchsmith] ' + (str(error) if isinstance(error, ValueError) else type(error).__name__ + ': update/rollback failed'), file=sys.stderr)
        return 1
    finally:
        if lock is not None:
            lock.close()


if __name__ == '__main__':
    sys.exit(main())
