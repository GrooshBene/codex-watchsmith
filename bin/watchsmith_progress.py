#!/usr/bin/env python3
"""Coordinate semantic progress and fallback for one wrapped process, not a Codex turn."""
import argparse
import copy
from datetime import datetime, timezone
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

TYPES = ('progress', 'segmented_progress', 'timer', 'alert', 'stats', 'metrics')


def content(value):
    """Validate bounded, explicitly supplied display data; never inspect task logs."""
    if not isinstance(value, dict) or value.get('type') not in TYPES:
        raise ValueError('unsupported activity type')
    allowed = {'type', 'title', 'subtitle', 'message', 'percentage', 'current_step',
               'number_of_steps', 'metrics', 'color', 'icon', 'badge',
               'counts_down', 'timer_start_at'}
    if set(value) - allowed or len(json.dumps(value, allow_nan=False).encode()) > 4096:
        raise ValueError('invalid or oversized display content')
    result = copy.deepcopy(value)
    def number(v):
        return type(v) in (int, float) and math.isfinite(v)
    for field in ('title', 'subtitle', 'message'):
        if field in result and (not isinstance(result[field], str) or len(result[field]) > 240):
            raise ValueError('invalid display text')
    kind = result['type']
    if kind == 'progress':
        v = result.get('percentage')
        if not number(v) or not 0 <= v <= 100:
            raise ValueError('progress requires a percentage from 0 to 100')
    elif kind == 'segmented_progress':
        step, total = result.get('current_step'), result.get('number_of_steps')
        if type(step) is not int or type(total) is not int or not 1 <= step <= total <= 100:
            raise ValueError('segmented progress requires valid current and total steps')
    elif kind in ('stats', 'metrics'):
        values = result.get('metrics')
        if not isinstance(values, list) or not 1 <= len(values) <= 8:
            raise ValueError('numeric displays require explicit measured values')
        for row in values:
            if not isinstance(row, dict) or set(row) - {'label', 'value', 'unit'}:
                raise ValueError('invalid metric')
            if not isinstance(row.get('label'), str) or not row['label'] or len(row['label']) > 80:
                raise ValueError('invalid metric label')
            v = row.get('value')
            if not number(v) and not (kind == 'stats' and isinstance(v, str) and 0 < len(v) <= 80):
                raise ValueError('invalid metric value')
            if 'unit' in row and (not isinstance(row['unit'], str) or len(row['unit']) > 20):
                raise ValueError('invalid metric unit')
    elif kind == 'alert' and not result.get('message'):
        raise ValueError('alert requires a message')
    elif kind == 'timer':
        # Elapsed time only: do not invent deadlines or reset on handover.
        if result.get('counts_down', False) is not False:
            raise ValueError('only elapsed timers are supported by the wrapper')
        result['counts_down'] = False
        if 'timer_start_at' in result:
            if not isinstance(result['timer_start_at'], str):
                raise ValueError('invalid timer start')
            stamp = datetime.fromisoformat(result['timer_start_at'].replace('Z', '+00:00'))
            if stamp.tzinfo is None:
                raise ValueError('timer requires a timezone')
    return result


def selected(data, requested=None):
    current = data.get('content_state')
    if current is None:
        current = content(requested) if requested else {'type': 'progress', 'percentage': 0}
    elif requested is not None and requested.get('type') == current['type']:
        current = content(requested)
    else:
        current = content(current)
    if current['type'] == 'timer':
        current['timer_start_at'] = data.get('content_state', {}).get('timer_start_at') or current.get('timer_start_at') or datetime.fromtimestamp(data.get('started_at', time.time()), timezone.utc).isoformat()
    data['content_state'] = current
    return copy.deepcopy(current)


def display(data, code=None):
    result = selected(data)
    result.update(title='Codex 작업 중' if code is None else 'Codex 실행 종료',
                  subtitle='실행이 계속되고 있습니다' if code is None else
                  ('명령이 종료되었습니다' if code == 0 else '명령이 정상 종료되지 않았습니다'),
                  color='blue' if code is None else ('green' if code == 0 else 'red'))
    if result['type'] == 'alert':
        result['message'] = result['subtitle']
    if code is not None:
        result['auto_dismiss_minutes'] = 0
        if result['type'] == 'timer':
            result.update(is_running=False, timer_pause_at=datetime.now(timezone.utc).isoformat())
        if 'badge' in result:
            result['badge'] = {'title': '실행 종료' if code == 0 else '실행 실패'}
    return result


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


def claim(path, now=None, content_state=None):
    if content_state is not None:
        content_state = content(content_state)
    now = time.time() if now is None else now
    with state(path) as data:
        if data['closed']:
            return {'action': 'skip', 'reason': 'run-ended'}
        if data.get('approval_gate'):
            return {'action': 'wait', 'reason': 'approval-transition'}
        if data['pending_until'] > now:
            return {'action': 'wait'}
        requested_type = content_state.get('type') if content_state else None
        chosen = selected(data, content_state)
        token = secrets.token_hex(24)
        data['previous_stream'] = data['may_have_stream']
        data.update(token=token, pending_until=now + LEASE, may_have_stream=True)
        return {'action': 'send', 'token': token, 'stream_key': data['stream_key'],
                'content_state_type': chosen['type'], 'content_state': chosen,
                'type_locked': requested_type is not None and requested_type != chosen['type'],
                'lease_seconds': LEASE}


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


def approval_transition(path, operation, now=None):
    """Fence local writers before pausing/resuming the remote progress stream."""
    if operation not in ('pause', 'resume'):
        raise ValueError('invalid approval transition')
    now = time.time() if now is None else now
    with state(path) as data:
        if data['closed']:
            return {'action': 'skip', 'reason': 'run-ended'}
        gate = data.get('approval_gate', '')
        if operation == 'pause' and gate == 'paused':
            return {'action': 'ready', 'reason': 'already-paused'}
        if (operation == 'pause' and gate) or (operation == 'resume' and gate != 'paused') or data['pending_until'] > now:
            return {'action': 'wait', 'reason': 'approval-transition'}
        token = secrets.token_hex(24)
        data.update(approval_gate='pausing' if operation == 'pause' else 'resuming',
                    approval_token=token, token='', pending_until=0)
        if operation == 'pause':
            data['approval_previous_stream'] = data['may_have_stream']
            data['may_have_stream'] = True  # Pause may create a retained remote key.
        chosen = selected(data)
        args = {'stream_key': data['stream_key']}
        if operation == 'pause':
            final = copy.deepcopy(chosen)
            final.update(title='사용자 선택 대기', subtitle='진행 표시를 멈추고 선택 알림으로 전환합니다',
                         color='orange', auto_dismiss_minutes=0)
            if final['type'] == 'alert':
                final['message'] = final['subtitle']
            if final['type'] == 'timer':
                final.update(is_running=False, timer_pause_at=datetime.now(timezone.utc).isoformat())
            args['content_state'] = final
        return {'action': 'send', 'token': token,
                'tool': 'pause_live_activity_stream' if operation == 'pause' else 'resume_live_activity_stream',
                'arguments': args}


def approval_finish(path, token, outcome):
    if outcome not in ('accepted', 'failed', 'unknown'):
        raise ValueError('invalid transition outcome')
    with state(path) as data:
        gate = data.get('approval_gate', '')
        if data['closed'] or not token or data.get('approval_token') != token or gate not in ('pausing', 'resuming'):
            return False
        data['approval_token'] = ''
        if outcome == 'unknown':
            data['approval_gate'] = gate + '-unknown'
        elif gate == 'pausing':
            data['approval_gate'] = 'paused' if outcome == 'accepted' else ''
            if outcome == 'accepted':
                data['semantic_active'] = True
                data['may_have_stream'] = True  # A paused remote key still needs cleanup.
            else:
                data['may_have_stream'] = data.get('approval_previous_stream', False)
        else:
            data['approval_gate'] = '' if outcome == 'accepted' else 'paused'
        return True


def ended(path):
    with state(path) as data:
        # The agent has explicitly acknowledged the remote end; keep fallback quiet.
        data.update(closed=True, semantic_active=True, may_have_stream=False, token='', pending_until=0)


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
        if (data['closed'] or data.get('approval_gate') or data['semantic_active'] or data['pending_until'] > now
                or data['fallback_attempted']):
            return
        data['fallback_attempted'] = True
        # Retire expired claims; their late acknowledgments cannot change ownership.
        data.update(token='', pending_until=0)
        help_result = invoke(cli, ['activity', 'stream', '--help'], env)
        if help_result is not None and help_result.returncode == 0:
            # Share the MCP key and type, including after an uncertain MCP outcome.
            if 'content_state' not in data and data.get('schema_version') == 2:
                selected(data, {'type': 'timer', 'counts_down': False})
            data['may_have_stream'] = True
            invoke(cli, ['activity', 'stream', data['stream_key'], '--content-state',
                         json.dumps(display(data))], env)
        elif not data['may_have_stream']:
            invoke(cli, ['push', '--title', 'Codex 작업 진행 중',
                         '--message', '설정한 대기 시간을 넘어 실행이 계속되고 있습니다.'], env)


def close_run(path, cli, env, code):
    with state(path) as data:
        data['closed'] = True
        end = data['may_have_stream'] or bool(data['token'])
        key = data['stream_key']
        final = display(data, code) if end else None
    if end:
        invoke(cli, ['activity', 'end-stream', key, '--content-state', json.dumps(final)], env)



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
        path.write_text(json.dumps({'schema_version': 2, 'started_at': time.time(),
                                   'stream_key': 'watchsmith-' + secrets.token_hex(16),
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
                    except (OSError, ValueError, KeyError, TypeError):
                        monitoring = False
                        print('[watchsmith] progress state unavailable; command continues', file=sys.stderr)
                time.sleep(.2)
            code = child.returncode
            try:
                close_run(path, cli, env, code)
            except (OSError, ValueError, KeyError, TypeError):
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
    claimant = sub.add_parser('claim')
    claimant.add_argument('--content-state', help='reviewed JSON display; first claimant selects type')
    sub.add_parser('ended')
    sub.add_parser('approval-pause')
    sub.add_parser('approval-resume')
    transition_ack = sub.add_parser('approval-finish')
    transition_ack.add_argument('--token', required=True)
    transition_ack.add_argument('--outcome', choices=('accepted', 'failed', 'unknown'), required=True)
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
        if args.action in ('approval-pause', 'approval-resume'):
            print(json.dumps(approval_transition(path, args.action.split('-')[1])))
            return 0
        if args.action == 'approval-finish':
            print(json.dumps({'recorded': approval_finish(path, args.token, args.outcome)}))
            return 0
        result = claim(path, content_state=json.loads(args.content_state) if args.content_state else None) if args.action == 'claim' else {
            'recorded': finish(path, args.token, args.outcome)}
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print('[watchsmith] progress context unavailable; do not infer another run', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
