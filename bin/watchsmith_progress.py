#!/usr/bin/env python3
"""Coordinate semantic progress and fallback for one wrapped process, not a Codex turn."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time

CONTEXT = 'WATCHSMITH_PROGRESS_CONTEXT'
LEASE = 90


@contextmanager
def state(path):
    # The wrapper owns a private directory; keep the inode stable for flock.
    with Path(path).open('r+') as file:
        fcntl.flock(file, fcntl.LOCK_EX)
        data = json.load(file)
        yield data
        file.seek(0)
        json.dump(data, file)
        file.truncate()
        file.flush()


def claim(path, now=None):
    now = time.time() if now is None else now
    with state(path) as data:
        if data['closed']:
            return {'action': 'skip', 'reason': 'run-ended'}
        if data['pending_until'] > now:
            return {'action': 'wait'}
        token = secrets.token_hex(24)
        data['previous_stream'] = data['may_have_stream']
        data.update(token=token, pending_until=now + LEASE, may_have_stream=True)
        return {'action': 'send', 'token': token, 'stream_key': data['stream_key'],
                'content_state_type': 'progress', 'lease_seconds': LEASE}


def finish(path, token, outcome):
    with state(path) as data:
        if data['closed'] or data['token'] != token:
            return False
        data.update(token='', pending_until=0)
        # An uncertain update must not erase an earlier acknowledged activity.
        if outcome == 'accepted':
            data['semantic_active'] = True
        data['may_have_stream'] = (data.get('previous_stream', False)
                                   or outcome in ('accepted', 'unknown'))
        return True


def ended(path):
    with state(path) as data:
        # The agent has explicitly acknowledged the remote end; keep fallback quiet.
        data.update(semantic_active=True, may_have_stream=False, token='', pending_until=0)


def invoke(cli, args, env):
    try:
        return subprocess.run([cli, *args], env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None


def fallback(path, cli, env, now=None):
    now = time.time() if now is None else now
    with state(path) as data:
        if (data['closed'] or data['semantic_active'] or data['pending_until'] > now
                or data['fallback_attempted']):
            return
        data['fallback_attempted'] = True
        # Retire expired claims; their late acknowledgments cannot change ownership.
        data.update(token='', pending_until=0)
        help_result = invoke(cli, ['activity', 'stream', '--help'], env)
        if help_result is not None and help_result.returncode == 0:
            # Share the MCP key and type, including after an uncertain MCP outcome.
            data['may_have_stream'] = True
            invoke(cli, ['activity', 'stream', data['stream_key'], '--content-state',
                         json.dumps({'type': 'progress', 'title': 'Codex 작업 중',
                                     'subtitle': '실행이 계속되고 있습니다', 'percentage': 0})], env)
        elif not data['may_have_stream']:
            invoke(cli, ['push', '--title', 'Codex 작업 진행 중',
                         '--message', '설정한 대기 시간을 넘어 실행이 계속되고 있습니다.'], env)


def close_run(path, cli, env, code):
    with state(path) as data:
        data['closed'] = True
        end = data['may_have_stream'] or bool(data['token'])
        key = data['stream_key']
    if end:
        invoke(cli, ['activity', 'end-stream', key, '--content-state', json.dumps({
            'type': 'progress', 'title': 'Codex 실행 종료',
            'subtitle': '명령이 종료되었습니다' if code == 0 else '명령이 정상 종료되지 않았습니다',
            'percentage': 100 if code == 0 else 0,
            'auto_dismiss_minutes': 0})], env)


def run(command):
    try:
        threshold = float(os.environ.get('CODEX_WATCH_THRESHOLD_SECONDS', '60'))
        if not math.isfinite(threshold) or threshold < 0:
            raise ValueError()
    except ValueError:
        print('[watchsmith] threshold must be a finite nonnegative number', file=sys.stderr)
        return 2
    cli = shutil.which('activitysmith')
    if not cli:
        print('[watchsmith] activitysmith CLI not found', file=sys.stderr)
        return 127
    env = dict(os.environ)
    if not env.get('ACTIVITYSMITH_API_KEY'):
        try:
            key = subprocess.run(['security', 'find-generic-password', '-a', env.get('USER', ''),
                                  '-s', 'activitysmith-codex', '-w'], capture_output=True,
                                 text=True, timeout=10)
            if key.returncode == 0:
                env['ACTIVITYSMITH_API_KEY'] = key.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    with tempfile.TemporaryDirectory(prefix='watchsmith-progress-') as directory:
        path = Path(directory) / 'state.json'
        path.write_text(json.dumps({'stream_key': 'watchsmith-' + secrets.token_hex(16),
                                   'closed': False, 'token': '', 'pending_until': 0,
                                   'semantic_active': False, 'may_have_stream': False,
                                   'fallback_attempted': False}))
        path.chmod(0o600)
        env[CONTEXT] = str(path)
        env['WATCHSMITH_PROGRESS_HELPER'] = str(Path(__file__).resolve())
        try:
            child = subprocess.Popen(command, env=env)
        except OSError:
            print('[watchsmith] could not start command', file=sys.stderr)
            return 127
        handlers = {}
        def forward(signum, frame):
            if child.poll() is None:
                child.send_signal(signum)
        for sig in (signal.SIGINT, signal.SIGTERM):
            handlers[sig] = signal.signal(sig, forward)
        deadline = time.monotonic() + threshold
        monitoring = True
        try:
            while child.poll() is None:
                if monitoring and time.monotonic() >= deadline:
                    try:
                        fallback(path, cli, env)
                    except (OSError, ValueError, KeyError):
                        monitoring = False
                        print('[watchsmith] progress state unavailable; command continues', file=sys.stderr)
                time.sleep(.2)
            code = child.returncode
            try:
                close_run(path, cli, env, code)
            except (OSError, ValueError, KeyError):
                print('[watchsmith] stream cleanup unavailable', file=sys.stderr)
            return code if code >= 0 else 128 - code
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    runner = sub.add_parser('run')
    runner.add_argument('command', nargs=argparse.REMAINDER)
    sub.add_parser('claim')
    sub.add_parser('ended')
    ack = sub.add_parser('finish')
    ack.add_argument('--token', required=True)
    ack.add_argument('--outcome', choices=('accepted', 'failed', 'unknown'), required=True)
    args = parser.parse_args()
    if args.action == 'run':
        command = args.command[1:] if args.command[:1] == ['--'] else args.command
        if not command:
            parser.error('a command is required')
        return run(command)
    path = os.environ.get(CONTEXT)
    if not path:
        print(json.dumps({'action': 'unavailable', 'reason': 'outside-wrapper'}))
        return 0
    try:
        if args.action == 'ended':
            ended(path)
            print(json.dumps({'recorded': True}))
            return 0
        result = claim(path) if args.action == 'claim' else {
            'recorded': finish(path, args.token, args.outcome)}
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, KeyError):
        print('[watchsmith] progress context unavailable; do not infer another run', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
