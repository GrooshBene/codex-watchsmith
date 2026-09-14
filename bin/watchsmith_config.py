#!/usr/bin/env python3
"""Validate and replace only the root notify setting, preserving other TOML text."""
import json
import os
from pathlib import Path
import sys
import tempfile
import tomllib
import uuid


def atomic_write(path, text):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
        if path.exists():
            os.chmod(name, path.stat().st_mode & 0o777)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def argv_value(value):
    if not isinstance(value, list) or not all(isinstance(arg, str) for arg in value):
        raise ValueError('notify must be an array of strings')
    return value


def replace_notify(text, replacement):
    data = tomllib.loads(text)
    line = '' if replacement is None else 'notify = ' + json.dumps(replacement, ensure_ascii=False) + '\n'
    if 'notify' not in data:
        return line + text
    argv_value(data['notify'])
    lines = text.splitlines(keepends=True)
    start = 0
    for end in range(1, len(lines) + 1):
        try:
            prefix = tomllib.loads(''.join(lines[:end]))
        except tomllib.TOMLDecodeError:
            continue
        if 'notify' in prefix:
            return ''.join(lines[:start]) + line + ''.join(lines[end:])
        start = end
    raise ValueError('cannot locate root notify safely')


def configure(mode, home):
    cfg = home / 'config.toml'
    state = home / 'watchsmith'
    previous = state / 'previous_notify.json'
    dispatcher = ['python3', str(home / 'bin' / 'watchsmith_notify_dispatcher.py')]
    text = cfg.read_text() if cfg.exists() else ''
    data = tomllib.loads(text)
    old = argv_value(data['notify']) if 'notify' in data else None
    if mode == 'install':
        if old == dispatcher:
            if not previous.exists():
                raise ValueError('dispatcher is configured but previous_notify.json is missing; restore a backup before reinstalling')
            saved = json.loads(previous.read_text())
            if saved is not None:
                argv_value(saved)
            return
        updated = replace_notify(text, dispatcher)
        saved = old
    else:
        if old != dispatcher:
            return  # Respect a notifier the user changed after installation.
        if not previous.exists():
            raise ValueError('previous_notify.json is missing; restore a backup before uninstalling')
        saved = json.loads(previous.read_text())
        if saved is not None:
            argv_value(saved)
        updated = replace_notify(text, saved)
    tomllib.loads(updated)
    state.mkdir(parents=True, exist_ok=True)
    atomic_write(state / ('config.toml.backup.' + uuid.uuid4().hex), text)
    if mode == 'install':
        atomic_write(previous, json.dumps(saved, ensure_ascii=False) + '\n')
    atomic_write(cfg, updated)


POLICY_BEGIN = '<!-- BEGIN codex-watchsmith activitysmith workflow -->'
POLICY_END = '<!-- END codex-watchsmith activitysmith workflow -->'


def policy_text(home):
    path = home / 'AGENTS.md'
    old = path.read_text() if path.exists() else ''
    template = (Path(__file__).resolve().parent.parent / 'config/activitysmith-agents.md').read_text().rstrip()
    legacy_begin = '<!-- BEGIN activitysmith autonomous workflow -->'
    legacy_end = '<!-- END activitysmith autonomous workflow -->'
    has_current = POLICY_BEGIN in old or POLICY_END in old
    has_legacy = legacy_begin in old or legacy_end in old
    if has_current and has_legacy:
        raise ValueError('both legacy and current policy blocks exist; review before migration')
    begin, ending = (legacy_begin, legacy_end) if has_legacy else (POLICY_BEGIN, POLICY_END)
    if not old.count(begin) and not old.count(ending):
        return old, old + ('\n\n' if old else '') + template + '\n'
    if old.count(begin) != 1 or old.count(ending) != 1:
        raise ValueError('ambiguous Watchsmith policy markers; review AGENTS.md before reinstalling')
    start, end = old.index(begin), old.index(ending)
    if end < start:
        raise ValueError('invalid Watchsmith policy marker order')
    return old, old[:start] + template + old[end + len(ending):]


def install_policy(home):
    old, updated = policy_text(home)
    if old == updated:
        return
    state = home / 'watchsmith'
    state.mkdir(parents=True, exist_ok=True)
    atomic_write(state / ('AGENTS.md.backup.' + uuid.uuid4().hex), old)
    atomic_write(home / 'AGENTS.md', updated)


if __name__ == '__main__':
    try:
        mode, home = sys.argv[1], Path(sys.argv[2]).expanduser().resolve()
        if mode == 'policy':
            install_policy(home)
        elif mode == 'install':
            policy_text(home)  # Reject malformed policy before mutating notify.
            configure(mode, home)
        elif mode == 'uninstall':
            configure(mode, home)
        else:
            raise ValueError('unknown configuration operation')
    except (ValueError, OSError) as exc:
        print(f'[watchsmith] configuration unchanged: {exc}', file=sys.stderr)
        raise SystemExit(1)
