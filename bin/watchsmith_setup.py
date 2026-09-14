#!/usr/bin/env python3
"""Interactive setup and read-only local diagnostics. Never display credentials."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tomllib


def run(argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None


def key_present():
    result = run(['security', 'find-generic-password', '-a', os.environ.get('USER', ''), '-s', 'activitysmith-codex'])
    return result is not None and result.returncode == 0


def diagnose(home):
    rows = []
    def add(name, state, detail):
        rows.append({'check': name, 'status': state, 'detail': detail})
    add('macOS', 'ok' if platform.system() == 'Darwin' else 'error', 'macOS is required')
    add('Python', 'ok' if sys.version_info >= (3, 11) else 'error', 'Python 3.11+ is required')
    for command in ('zsh', 'activitysmith'):
        add(command, 'ok' if shutil.which(command) else 'error', 'available' if shutil.which(command) else 'not found on PATH')
    add('Codex CLI', 'ok' if shutil.which('codex') else 'info', 'optional for Desktop; required for wrapped CLI tasks')
    has_key = key_present()
    add('Keychain', 'ok' if has_key else 'warning', 'key entry present (validity untested)' if has_key else 'run watchsmith setup to register a key')
    data = {}
    manifest = home / 'watchsmith/installation.json'
    try:
        data = json.loads(manifest.read_text())
        hashes = data['installed_hashes']
        if not isinstance(hashes, dict) or not hashes:
            raise ValueError()
        valid = True
        for name, digest in hashes.items():
            path = Path(name)
            if path.is_absolute() or '..' in path.parts or len(path.parts) != 2 or path.parts[0] != 'bin':
                raise ValueError()
            target = home / path
            valid &= target.is_file() and not target.is_symlink() and hashlib.sha256(target.read_bytes()).hexdigest() == digest
        add('Installed files', 'ok' if valid else 'error', 'match recorded hashes' if valid else 'missing or modified; review before reinstalling')
    except (OSError, ValueError, KeyError, TypeError):
        data = {}
        add('Installed files', 'error', 'installation record missing or invalid; run setup')
    try:
        config = tomllib.loads((home / 'config.toml').read_text())
        from watchsmith_install import computer_wrapper, is_dispatcher, validate_chain
        notify = config.get('notify')
        envelope = computer_wrapper(notify)
        dispatcher = str(home / 'bin/watchsmith_notify_dispatcher.py')
        linked = is_dispatcher(notify, dispatcher) or bool(envelope and is_dispatcher(envelope[1], dispatcher))
        saved = json.loads((home / 'watchsmith/previous_notify.json').read_text())
        validate_chain(saved, dispatcher)
        if saved != data.get('installed_previous_notify'):
            linked = False
        if envelope and computer_wrapper(saved):
            linked = False
        add('Completion hook', 'ok' if linked else 'error', 'linked (delivery untested)' if linked else 'connection needs review')
        mcp = config.get('mcp_servers', {})
        configured = any('activitysmith' in name.lower() for name in mcp)
        add('MCP', 'info', 'config entry found; authorization unverified' if configured else 'connect ActivitySmith MCP separately; plugin connections may not appear here')
    except (OSError, ValueError, KeyError, TypeError):
        add('Completion hook', 'error', 'configuration or saved connection invalid')
    try:
        policy = (home / 'AGENTS.md').read_text()
        valid = policy.count('<!-- BEGIN codex-watchsmith activitysmith workflow -->') == 1 and policy.count('<!-- END codex-watchsmith activitysmith workflow -->') == 1 and '<!-- BEGIN activitysmith autonomous workflow -->' not in policy
        add('Agent policy', 'ok' if valid else 'warning', 'managed policy present' if valid else 'missing or ambiguous policy')
    except OSError:
        add('Agent policy', 'warning', 'policy missing')
    add('Command path', 'ok' if shutil.which('watchsmith') and Path(shutil.which('watchsmith')).resolve() == (home / 'bin/watchsmith').resolve() else 'warning', 'open a new terminal after PATH setup')
    return rows


def confirm(message):
    return input(message + ' [y/N] ').strip().lower() in ('y', 'yes')


def configure_path(home, shellfile):
    if shellfile.is_symlink():
        raise ValueError('shell configuration is a symlink; add PATH manually')
    old = shellfile.read_text() if shellfile.exists() else ''
    import shlex
    line = 'export PATH=' + shlex.quote(str(home / 'bin')) + ':"$PATH"'
    if line in old.splitlines():
        return False
    # Save an exact private backup before changing personal shell configuration.
    from watchsmith_install import put, encode
    import time
    backup = home / 'watchsmith/setup-backups' / (str(time.time_ns()) + '.zshrc')
    put(backup, encode(old.encode()))
    put(shellfile, encode((old + '\n# Watchsmith commands\n' + line + '\n').encode(), shellfile.stat().st_mode & 0o777 if shellfile.exists() else 0o600))
    return True


def setup(home, source=None):
    if not sys.stdin.isatty():
        print('Setup needs an interactive terminal. Use doctor --json for unattended diagnostics.', file=sys.stderr)
        return 2
    if platform.system() != 'Darwin' or not shutil.which('zsh'):
        print('Setup requires macOS and zsh.')
        return 1
    print('Watchsmith setup — existing credentials and personal settings are preserved.')
    if not shutil.which('activitysmith'):
        if not shutil.which('npm'):
            print('Install Node.js/npm, then run setup again: https://nodejs.org/en/download')
            return 1
        if not confirm('Install ActivitySmith CLI with npm?'):
            return 1
        try:
            subprocess.run(['npm', 'install', '-g', 'activitysmith-cli@latest'], check=True, timeout=300,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            print('CLI installation failed. Run npm install -g activitysmith-cli@latest manually and retry.')
            return 1
        if not shutil.which('activitysmith'):
            print('CLI is not on PATH. Open a new terminal and retry.')
            return 1
    if source:
        env = dict(os.environ, CODEX_HOME=str(home))
        command = [sys.executable, str(source / 'bin/watchsmith_install.py'), 'install']
        try:
            check = subprocess.run(command + ['--check'], env=env, capture_output=True, text=True, timeout=30)
            if check.returncode:
                print('Installation preflight failed. Run install.sh --check from this package for details.')
                return 1
            changes = json.loads(check.stdout)['changes']
            print(f'Installation location: {home}\nManaged files to change: {len(changes)}')
            if changes:
                if not confirm('Finish other Codex/watchdog jobs and close affected clients. Apply installation now?'):
                    return 1
                subprocess.run(command + ['--upgrade', '--quiesced'], env=env, check=True, timeout=60,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, ValueError, subprocess.SubprocessError):
            print('Installation did not complete. Inspect the installer recovery report before retrying.')
            return 1
    elif not (home / 'watchsmith/installation.json').exists():
        print('Installation is missing. Start from a verified release package.')
        return 1
    path_saved = False
    connection_unverified = False
    if not key_present():
        print('Create an API key after pairing your phone: https://activitysmith.com/quickstart')
        if confirm('Register an API key in macOS Keychain now?'):
            subprocess.run(['zsh', str(home / 'bin/activitysmith-keychain-setup')], check=True)
    if confirm('Ensure Watchsmith commands are available in future zsh terminals?'):
        configure_path(home, Path.home() / '.zshrc')
        path_saved = True
    print('For semantic progress, connect ActivitySmith MCP separately:\nhttps://activitysmith.com/integrations/mcp-server')
    if key_present() and confirm('Send one test notification to your paired device?'):
        # Use Keychain explicitly, never a stale environment key.
        from activitysmith_notify import get_key
        os.environ.pop('ACTIVITYSMITH_API_KEY', None)
        key = get_key()
        response = None
        if key:
            try:
                response = subprocess.run([shutil.which('activitysmith'), 'push', '--title', 'Watchsmith setup',
                    '--message', 'Installation connection test'], env=dict(os.environ, ACTIVITYSMITH_API_KEY=key),
                    capture_output=True, text=True, timeout=30)
            except (OSError, subprocess.SubprocessError):
                pass
        result = 'accepted' if response and response.returncode == 0 and 'Success: true' in response.stdout else 'unknown'
        print('Notification service result: ' + result)
        if result == 'accepted':
            seen = confirm('Did the notification appear on your phone?')
            print('Phone display confirmed.' if seen else 'Phone display remains unverified.')
            connection_unverified = not seen
        else:
            connection_unverified = True
            print('Check device/account connectivity. To replace the key, run activitysmith-keychain-setup.')
    rows = diagnose(home)
    for row in rows:
        if row['check'] == 'Command path' and path_saved:
            row.update(status='info', detail='PATH saved; open a new terminal')
        print(f'[{row["status"]}] {row["check"]}: {row["detail"]}')
    print('Restart Codex and open a new terminal. Run watchsmith setup again to finish skipped steps.')
    return 1 if connection_unverified or any(r['status'] in ('error', 'warning') for r in rows) else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('setup', 'doctor'))
    parser.add_argument('--json', action='store_true', help='doctor only; no network or notification')
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    source = root if (root / 'config/activitysmith-agents.md').exists() and (root / 'install.sh').exists() else None
    home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).expanduser().resolve() if source else root
    try:
        if args.command == 'doctor':
            rows = diagnose(home)
            print(json.dumps(rows, indent=2) if args.json else '\n'.join(f'[{r["status"]}] {r["check"]}: {r["detail"]}' for r in rows))
            return 1 if any(r['status'] in ('error', 'warning') for r in rows) else 0
        if args.json:
            parser.error('--json is only supported by doctor')
        return setup(home, source)
    except (OSError, ValueError, subprocess.SubprocessError, EOFError, KeyboardInterrupt):
        print('Setup stopped; completed steps are preserved. Rerun to continue.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
