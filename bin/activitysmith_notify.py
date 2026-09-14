#!/usr/bin/env python3
"""Generic completion fallback, coordinated only for exact Codex event IDs."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
from watchsmith_delivery import Store, event_key, MARKER

SERVICE = 'activitysmith-codex'
HOME = Path(__file__).resolve().parent.parent


def get_key():
    if os.environ.get('ACTIVITYSMITH_API_KEY'):
        return os.environ['ACTIVITYSMITH_API_KEY']
    sec = shutil.which('security')
    if not sec:
        return None
    try:
        p = subprocess.run([sec, 'find-generic-password', '-a', os.environ.get('USER', ''), '-s', SERVICE, '-w'], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def deliver(cli, key, payload=None):
    env = os.environ.copy()
    env['ACTIVITYSMITH_API_KEY'] = key
    payload = payload or {'title': 'Codex 응답 종료', 'message': '결과 요약을 연결하지 못했습니다. Codex에서 확인해 주세요.'}
    args = [cli, 'push', '--title', payload['title'], '--message', payload['message']]
    if payload.get('subtitle'):
        args += ['--subtitle', payload['subtitle']]
    try:
        p = subprocess.run(args, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=30)
        # CLI 1.10 reports this explicit server response. Other output is unknown.
        if p.returncode == 0 and 'Success: true' in p.stdout:
            return 'accepted'
        return 'unknown'  # Failure may have occurred after remote acceptance.
    except subprocess.TimeoutExpired:
        return 'unknown'
    except OSError:
        return 'failed'  # CLI could not be started.


def main():
    if len(sys.argv) != 2:
        return 0
    try:
        evt = json.loads(sys.argv[1])
    except (ValueError, TypeError):
        return 0
    if not isinstance(evt, dict) or evt.get('type') != 'agent-turn-complete':
        return 0
    cli = shutil.which('activitysmith')
    key = get_key() if cli else None
    if not cli or not key:
        return 0
    store = None
    claim = None
    identity = None
    try:
        try:
            identity = event_key(evt.get('thread-id'), evt.get('turn-id'))
        except ValueError:
            pass  # Older clients retain best-effort generic completion.
        preview = None
        try:
            final_text = evt.get('last-assistant-message')
            if identity or (isinstance(final_text, str) and MARKER.search(final_text)):
                store = Store(HOME)
                prepared = store.summary(evt)
                if prepared:
                    identity, preview = prepared
        except (OSError, ValueError, sqlite3.Error):
            if store:
                store.close()
            store = None
        if identity:
            try:
                if store is None:
                    store = Store(HOME)
                # A detached notifier worker may wait; dispatcher never blocks old hooks.
                deadline = time.monotonic() + 125
                while True:
                    claim = store.claim(identity, 'generic', lease=45)
                    if claim['action'] != 'wait':
                        break
                    if time.monotonic() >= deadline:
                        return 0
                    time.sleep(min(claim['retry_after'], 1))
                if claim['action'] == 'skip':
                    return 0
            except (OSError, sqlite3.Error):
                claim = None
                print('[watchsmith] delivery store unavailable; generic fallback is not deduplicated', file=sys.stderr)
        outcome = deliver(cli, key, preview) if preview else deliver(cli, key)
        if store and claim:
            try:
                store.finish(identity, claim['token'], outcome)
            except sqlite3.Error:
                pass  # Ambiguous persistence does not justify resending.
        return 0
    finally:
        if store:
            store.close()


if __name__ == '__main__':
    raise SystemExit(main())
