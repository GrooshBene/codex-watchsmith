#!/usr/bin/env python3
"""Inspect, install, restore, and recover Watchsmith files without changing other hooks."""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
import time
import uuid
from watchsmith_config import argv_value, policy_text, replace_notify
import tomllib

ROOT = Path(__file__).resolve().parent.parent
NAMES = ('activitysmith_notify.py', 'watchsmith_notify_dispatcher.py', 'codex-watch',
         'activitysmith-keychain-setup', 'activitysmith-test', 'watchsmith_result.py', 'watchsmith_delivery.py', 'watchsmith_progress.py', 'watchsmith', 'watchsmith_update.py',
         'watchsmith_install.py', 'watchsmith_config.py')
TRACKED = ['bin/' + n for n in NAMES] + ['config.toml', 'AGENTS.md', 'watchsmith/previous_notify.json', 'watchsmith/installation.json']


def image(path):
    if path.is_symlink():
        raise ValueError('managed paths must not be symlinks; review installation manually')
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError('managed path is not a regular file')
    return {'data': base64.b64encode(path.read_bytes()).decode(), 'mode': path.stat().st_mode & 0o777}


def content(item):
    return base64.b64decode(item['data']) if item else b''


def encode(data, mode=0o600):
    return {'data': base64.b64encode(data).decode(), 'mode': mode}


def digest(item):
    return hashlib.sha256(content(item)).hexdigest() if item else None


def put(path, item):
    if item is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content(item))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, item['mode'])
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path, data):
    put(path, encode((json.dumps(data, indent=2) + '\n').encode()))


def read_json(item):
    return json.loads(content(item)) if item else None


def is_dispatcher(argv, path):
    if not isinstance(argv, list):
        return False
    if len(argv) == 2 and isinstance(argv[0], str) and Path(argv[0]).name.startswith('python3'):
        target = argv[1]
    elif len(argv) == 1:
        target = argv[0]
    else:
        return False
    return isinstance(target, str) and Path(target).is_absolute() and Path(target).resolve() == Path(path).resolve()


def validate_chain(argv, dispatcher, depth=0):
    if argv is None:
        return False
    argv_value(argv)
    if not argv:
        return False
    if depth > 8 or is_dispatcher(argv, dispatcher):
        raise ValueError('saved notifier contains a dispatcher cycle or excessive nesting')
    computer = Path(argv[0]).name == 'SkyComputerUseClient' and 'turn-ended' in argv
    # Only interpret the known Computer Use argv shape, never arbitrary command strings.
    if computer and '--previous-notify' in argv:
        index = argv.index('--previous-notify')
        if index + 1 >= len(argv):
            raise ValueError('Computer Use previous notifier value is missing')
        nested = json.loads(argv[index + 1])
        validate_chain(nested, dispatcher, depth + 1)
    return computer


def computer_wrapper(argv):
    """Recognize only the observed Computer Use envelope; never arbitrary argv."""
    if not isinstance(argv, list) or len(argv) not in (2, 4):
        return None
    if Path(argv[0]).name != 'SkyComputerUseClient' or argv[1] != 'turn-ended':
        return None
    if len(argv) == 2:
        return argv[:2], None
    if argv[2] != '--previous-notify':
        return None
    nested = json.loads(argv[3])
    if nested is not None:
        argv_value(nested)
    return argv[:2], nested


def wrap_computer(prefix, nested):
    return prefix + ['--previous-notify', json.dumps(nested)] if nested else prefix


def prepare(home):
    before = {p: image(home / p) for p in TRACKED}
    text = content(before['config.toml']).decode()
    data = tomllib.loads(text)
    old = argv_value(data['notify']) if 'notify' in data else None
    dispatcher_path = str(home / 'bin/watchsmith_notify_dispatcher.py')
    dispatcher = ['python3', dispatcher_path]
    saved = read_json(before['watchsmith/previous_notify.json'])
    manifest = read_json(before['watchsmith/installation.json'])
    if manifest is not None and manifest.get('schema_version') != 1:
        raise ValueError('unsupported installation manifest')
    envelope = computer_wrapper(old)
    managed = is_dispatcher(old, dispatcher_path) or (
        envelope is not None and is_dispatcher(envelope[1], dispatcher_path))
    if managed:
        if before['watchsmith/previous_notify.json'] is None:
            raise ValueError('dispatcher configured but saved notifier is missing')
        if envelope and not manifest:
            raise ValueError('wrapped dispatcher requires installation manifest')
        if manifest and saved != manifest.get('installed_previous_notify', manifest['uninstall_notify']):
            raise ValueError('saved notifier was modified after installation')
        previous = saved
    else:
        previous = old
    computer = validate_chain(previous, dispatcher_path)
    target = dispatcher
    original = manifest['uninstall_notify'] if manifest else old
    # Keep Computer Use outside our dispatcher so restarting cannot add it again.
    if envelope:
        prefix = envelope[0]
        original_envelope = computer_wrapper(original)
        if managed and original_envelope and original_envelope[0] != prefix:
            raise ValueError('Computer Use executable changed; review original chain')
        if managed:
            saved_envelope = computer_wrapper(previous)
            if saved_envelope:
                if saved_envelope[0] != prefix:
                    raise ValueError('Computer Use executable changed; review saved chain')
                previous = saved_envelope[1]
            if not computer_wrapper(original):
                original = wrap_computer(prefix, original)
        else:
            previous = envelope[1]
        target = old if managed else wrap_computer(prefix, dispatcher)
        computer = True
    elif managed:
        saved_envelope = computer_wrapper(previous)
        if saved_envelope:
            target = wrap_computer(saved_envelope[0], dispatcher)
            previous = saved_envelope[1]
            computer = True
    validate_chain(previous, dispatcher_path)
    old_policy, new_policy = policy_text(home)
    known = json.loads((ROOT / 'config/known-runtime-hashes.json').read_text())
    after = dict(before)
    for name in NAMES:
        key = 'bin/' + name
        source = encode((ROOT / key).read_bytes(), 0o755)
        current = before[key]
        accepted = set(known.get(name, [])) | {digest(source)}
        if manifest:
            accepted.add(manifest.get('installed_hashes', {}).get(key))
        if current and digest(current) not in accepted:
            raise ValueError(f'user-modified or unrecognized runtime: {name}; no files changed')
        after[key] = source
    cfg = replace_notify(text, target)
    after['config.toml'] = encode(cfg.encode(), before['config.toml']['mode'] if before['config.toml'] else 0o600)
    after['AGENTS.md'] = encode(new_policy.encode(), before['AGENTS.md']['mode'] if before['AGENTS.md'] else 0o600)
    after['watchsmith/previous_notify.json'] = encode((json.dumps(previous) + '\n').encode())
    # Existing dispatcher installs have no pre-Watchsmith executable snapshot: keep
    # their working helper set on uninstall rather than deleting unknown dependencies.
    baseline = {p: manifest['baseline'].get(p, before[p]) if manifest else before[p]
                for p in TRACKED if p != 'watchsmith/installation.json'}
    document = {'schema_version': 1, 'baseline': baseline,
                'baseline_was_dispatcher': manifest['baseline_was_dispatcher'] if manifest else is_dispatcher(old, dispatcher_path),
                'uninstall_notify': original,
                'installed_previous_notify': previous,
                'installed_hashes': {'bin/' + n: digest(after['bin/' + n]) for n in NAMES}}
    version_path = ROOT / 'VERSION'
    release_path = ROOT / 'release.json'
    release_info = json.loads(release_path.read_text()) if release_path.exists() else {}
    prior_release = manifest.get('release', {}) if manifest else {}
    package_hash = os.environ.get('WATCHSMITH_PACKAGE_SHA256')
    if not package_hash and release_info.get('commit') and prior_release.get('commit') == release_info['commit']:
        package_hash = prior_release.get('package_sha256')
    document['release'] = {'version': version_path.read_text().strip() if version_path.exists() else 'unknown',
                           'commit': release_info.get('commit'),
                           'package_sha256': package_hash,
                           'source': 'release' if release_info else 'checkout'}
    after['watchsmith/installation.json'] = encode((json.dumps(document, indent=2) + '\n').encode())
    kind = 'computer-use-wrapper' if computer else ('dispatcher' if is_dispatcher(old, dispatcher_path) else ('existing-notifier' if old else 'new'))
    return before, after, kind


def validate_runtime():
    with tempfile.TemporaryDirectory(prefix='watchsmith-validate-') as directory:
        for name in NAMES:
            src = ROOT / 'bin' / name
            if name.endswith('.py'):
                py_compile.compile(str(src), cfile=str(Path(directory) / (name + 'c')), doraise=True)
            else:
                subprocess.run(['zsh', '-o', 'NO_BG_NICE', '-n', str(src)], check=True, capture_output=True)


def pending_transaction(home):
    base = home / 'watchsmith/transactions'
    for path in sorted(base.glob('*/journal.json')) if base.exists() else []:
        journal = json.loads(path.read_text())
        if journal['status'] in ('applying', 'recovering', 'conflict'):
            return path, journal
    return None


def restore(home, journal_path, journal):
    if (set(journal['before']) != set(journal['after'])
            or not set(journal['before']).issubset(TRACKED)
            or not set(journal['changes']).issubset(journal['before'])):
        raise ValueError('invalid transaction paths')
    # Preflight all paths before undoing anything; never overwrite unrelated edits.
    for p in journal['changes']:
        if image(home / p) not in (journal['before'][p], journal['after'][p]):
            journal['status'] = 'conflict'
            write_json(journal_path, journal)
            raise ValueError('rollback conflict: preserve intervening edits and review the journal locally')
    journal['status'] = 'recovering'
    write_json(journal_path, journal)
    # Restore runtime dependencies before restoring configuration.
    ordered = sorted(journal['changes'], key=lambda p: p == 'config.toml')
    for p in ordered:
        if image(home / p) not in (journal['before'][p], journal['after'][p]):
            raise ValueError('file changed during recovery; manual review required')
        put(home / p, journal['before'][p])
    journal['status'] = 'rolled-back'
    write_json(journal_path, journal)


def transact(home, before, after, operation, writer=put):
    changes = [p for p in before if before[p] != after[p]]
    if not changes:
        return None
    for p in before:
        if image(home / p) != before[p]:
            raise ValueError('installation changed during inspection; inspect again')
    transaction = f'{time.time_ns()}-{uuid.uuid4().hex}'
    journal_path = home / 'watchsmith/transactions' / transaction / 'journal.json'
    journal = {'status': 'applying', 'operation': operation, 'before': before, 'after': after, 'changes': changes}
    write_json(journal_path, journal)
    try:
        # cfg last means old/new hooks see complete owned runtime after quiescence.
        for p in sorted(changes, key=lambda p: p == 'config.toml'):
            if image(home / p) != before[p]:
                raise ValueError('installation changed while applying')
            writer(home / p, after[p])
        journal['status'] = 'applied-local-verification-only'
        write_json(journal_path, journal)
    except Exception:
        restore(home, journal_path, journal)
        raise
    return transaction


def uninstall_plan(home):
    before = {p: image(home / p) for p in TRACKED}
    manifest = read_json(before['watchsmith/installation.json'])
    if not manifest or manifest.get('schema_version') != 1:
        raise ValueError('no migration manifest; inspect and upgrade first to preserve original helper dependencies')
    for key, expected in manifest['installed_hashes'].items():
        if digest(before[key]) != expected:
            raise ValueError('installed runtime changed; preserve it and review before removal')
    after = dict(before)
    text = content(before['config.toml']).decode()
    data = tomllib.loads(text)
    dispatcher = ['python3', str(home / 'bin/watchsmith_notify_dispatcher.py')]
    envelope = computer_wrapper(data.get('notify'))
    owned = is_dispatcher(data.get('notify'), dispatcher[1]) or (
        envelope is not None and is_dispatcher(envelope[1], dispatcher[1]))
    original_envelope = computer_wrapper(manifest['uninstall_notify'])
    if envelope and original_envelope and envelope[0] != original_envelope[0]:
        return before, after
    if not owned:
        # A changed notifier may depend on our files; preserve both until reviewed.
        return before, after
    if owned:
        if before['watchsmith/previous_notify.json'] is None:
            raise ValueError('saved notifier is missing; review installation manifest before removal')
        if read_json(before['watchsmith/previous_notify.json']) != manifest.get('installed_previous_notify', manifest['uninstall_notify']):
            raise ValueError('saved notifier was modified after installation; review before removal')
        original = manifest['uninstall_notify']
        if envelope and not computer_wrapper(original):
            original = wrap_computer(envelope[0], original)
        after['config.toml'] = encode(replace_notify(text, original).encode(), before['config.toml']['mode'])
    baseline = manifest['baseline']
    for name in NAMES:
        key = 'bin/' + name
        after[key] = baseline.get(key, before[key])
    # Preserve baseline metadata; policy and credentials remain for manual review.
    after['watchsmith/previous_notify.json'] = baseline['watchsmith/previous_notify.json']
    after['watchsmith/installation.json'] = None
    return before, after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['install', 'uninstall'])
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--upgrade', action='store_true')
    parser.add_argument('--quiesced', action='store_true', help='confirm affected Codex/watchdog processes have stopped')
    parser.add_argument('--rollback', metavar='TRANSACTION_ID')
    args = parser.parse_args()
    if args.check and args.rollback:
        parser.error('--check cannot be combined with --rollback')
    home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).expanduser().resolve()
    try:
        if (home / 'bin').is_symlink() or (home / 'watchsmith').is_symlink():
            raise ValueError('symlinked runtime/state directories require manual review')
        pending = pending_transaction(home)
        if args.rollback:
            if not args.quiesced:
                raise ValueError('stop affected Codex/watchdog processes and use --quiesced for rollback')
            base = home / 'watchsmith/transactions'
            if args.rollback == 'latest':
                paths = sorted(base.glob('*/journal.json'))
                if not paths:
                    raise ValueError('no transaction found')
                path = paths[-1]
            else:
                if Path(args.rollback).name != args.rollback or args.rollback in ('.', '..'):
                    raise ValueError('invalid transaction ID')
                path = base / args.rollback / 'journal.json'
            journal = json.loads(path.read_text())
            home.mkdir(parents=True, exist_ok=True)
            with (home / 'watchsmith/install.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                restore(home, path, journal)
            print('Rollback completed; already sent notifications are unaffected.')
            return 0
        if pending:
            raise ValueError('unfinished transaction; use --rollback ' + pending[0].parent.name + ' --quiesced')
        validate_runtime()
        if args.operation == 'install':
            before, after, kind = prepare(home)
        else:
            if not image(home / 'watchsmith/installation.json'):
                cfg = tomllib.loads((home / 'config.toml').read_text()) if (home / 'config.toml').exists() else {}
                if not is_dispatcher(cfg.get('notify'), str(home / 'bin/watchsmith_notify_dispatcher.py')):
                    print('No managed installation to remove; existing files preserved.')
                    return 0
            before, after = uninstall_plan(home)
            kind = 'managed-removal'
        changes = [p for p in before if before[p] != after[p]]
        print(json.dumps({'installation_type': kind, 'changes': changes,
                          'computer_use': 'external callback; installation check verifies configuration only' if kind == 'computer-use-wrapper' else 'not detected',
                          'agent_turn_correlation': 'requires exact trusted turn ID; never inferred',
                          'credentials': 'reused, not inspected or changed'}, indent=2))
        if args.check or not changes:
            return 0
        if any(before['bin/' + n] for n in NAMES) and not args.quiesced:
            raise ValueError('stop affected Codex/watchdog processes, then repeat with --quiesced')
        home.mkdir(parents=True, exist_ok=True)
        state = home / 'watchsmith'
        state.mkdir(exist_ok=True, mode=0o700)
        with (state / 'install.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if pending_transaction(home):
                raise ValueError('another unfinished transaction requires recovery')
            transaction = transact(home, before, after, args.operation)
        print('Local installation applied. Transaction: ' + str(transaction))
        print('Restart Codex and verify actual delivery/previous hooks. Keychain and MCP authorization are reused.')
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, py_compile.PyCompileError) as exc:
        print('[watchsmith] ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
