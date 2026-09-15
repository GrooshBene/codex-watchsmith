#!/usr/bin/env python3
"""Summarize the current completion event locally; coordinate exact event IDs."""
import json
import os
import re
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
from watchsmith_delivery import Store, event_key

SERVICE = 'activitysmith-codex'
HOME = Path(__file__).resolve().parent.parent


def excerpt(text, limit):
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def sentences(value):
    """Bounded local extraction, not a model call or a complete privacy filter."""
    if not isinstance(value, str):
        return []
    text = value[:64000]
    text = re.sub(r'<!--.*?(?:-->|\Z)', '', text, flags=re.S)
    text = re.sub(r'(?ms)^\s*(```|~~~).*?^\s*\1[^\n]*(?:\n|\Z)|^\s*(?:```|~~~).*\Z', '', text)
    text = re.sub(r'!?\[([^\]\n]*)\]\([^\n)]*\)', r'\1', text)
    text = re.sub(r'https?://\S+|(?:/Users/|/home/|/private/|~/|[A-Z]:\\)\S+|\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', '[비공개]', text)
    text = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:sk-|ghp_|github_pat_)[\w-]+', '[비공개]', text)
    result = []
    for line in text.splitlines():
        # Exclude obvious credentials, quoted source and machine directives.
        if re.search(r'(?i)password|passwd|secret|api[_ -]?key|access[_ -]?token|authorization|비밀번호|인증정보|비밀|기밀', line):
            continue
        if line.lstrip().startswith(('>', '::', '<', '{', '}', '|')):
            continue
        line = re.sub(r'^\s*(?:#{1,6}\s*|[-*+]\s+|\d+[.)]\s+)', '', line)
        line = re.sub(r'[`*_]', '', line)
        line = ' '.join(line.split())
        for part in re.split(r'(?<=[.!?。])\s+', line):
            if len(part) >= 4 and part not in result:
                result.append(part)
    return result[:200]


def request_sentences(value):
    """Remove known client envelopes; None means a reply-only current input."""
    if not isinstance(value, str):
        return []
    text = value[:64000]
    ambient = bool(re.search(r'<in-app-browser-context\b', text))
    text = re.sub(r'<in-app-browser-context\b[^>]*>.*?(?:</in-app-browser-context\s*>|\Z)', '', text, flags=re.S)
    reply = bool(re.search(r'<send_user_message_question_reply\b', text))
    text = re.sub(r'<send_user_message_question_reply\b[^>]*>.*?(?:</send_user_message_question_reply\s*>|\Z)', '', text, flags=re.S)
    if ambient or reply:
        text = re.sub(r'(?m)^\s*## My request:\s*$', '', text)
    # Some clients supply the response array without its enclosing tag.
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        data = None
    if isinstance(data, list) and data and all(
            isinstance(row, dict) and {'questionItemId', 'question', 'answer'} <= row.keys()
            for row in data):
        return None
    result = sentences(text)
    return result if result or not reply else None


def completion_payload(event):
    """Use only this event's request and answer; never guess a recent turn."""
    if os.environ.get('WATCHSMITH_COMPLETION_PREVIEW', '1') == '0':
        return {'title': 'Codex 응답 종료', 'message': '요청에 대한 응답이 끝났습니다.'}
    answer = sentences(event.get('last-assistant-message'))
    inputs = event.get('input-messages')
    request = []
    if isinstance(inputs, list):
        for value in reversed(inputs[-20:]):
            candidate = request_sentences(value)
            request = candidate or []
            # A current confirmation must not inherit an older task title.
            if request or candidate is None:
                break
    verification = next((s for s in answer if re.search(r'검증|테스트|tests?\b|verified|validation', s, re.I)), None)
    # Keep the leading outcome, plus a limitation even if it appears late.
    limitation = next((s for s in answer if re.search(r'못했|못한|미완료|미검증|미적용|차단|실패했|아직|남아|not (?:tested|verified|applied)|blocked|failed|unable', s, re.I)), None)
    primary = next((s for s in answer if len(s) >= 12), answer[0] if answer else '')
    pieces = [primary] if primary else []
    extra = limitation or next((s for s in answer if s != primary and s != verification and len(s) >= 12), None)
    if extra and extra != primary:
        pieces = [excerpt(primary, 100), excerpt(extra, 77)]
    topic = request[0] if request else (primary or 'Codex')
    if primary and re.fullmatch(r'(?:응|네|좋아|알겠어|그렇게|그거|진행|계속|해줘|해주세요|부탁해|go ahead|continue|yes|ok|please|[\s.!?,])+', topic, re.I):
        topic = primary
    payload = {'title': excerpt(topic, 60) + ' · 작업 결과',
               'message': excerpt(' '.join(pieces), 180) if pieces else '요청에 대한 응답이 끝났습니다. 자세한 내용은 Codex에서 확인해 주세요.'}
    if verification and verification not in pieces:
        payload['subtitle'] = excerpt(verification, 140)
    return payload


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
    payload = payload or completion_payload({})
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
        preview = completion_payload(evt)
        try:
            if identity and os.environ.get('WATCHSMITH_COMPLETION_PREVIEW', '1') != '0':
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
        outcome = deliver(cli, key, preview)
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
