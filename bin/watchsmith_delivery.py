#!/usr/bin/env python3
"""Local terminal-event coordination. No network or credential access."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import secrets
import sqlite3
import sys
import time

RETENTION = 7 * 24 * 3600
SUMMARY_TTL = 3600
MARKER = re.compile(r"(?:^|\n)<!-- watchsmith-result:([0-9a-f]{48}) -->\s*\Z")


def event_key(thread_id, turn_id):
    if not all(isinstance(v, str) and v.strip() and len(v) <= 512 for v in (thread_id, turn_id)):
        raise ValueError('exact thread-id and turn-id are required')
    return hashlib.sha256(json.dumps([thread_id, turn_id, 'terminal']).encode()).hexdigest()


def installed_home():
    return Path(__file__).resolve().parent.parent


class Store:
    def __init__(self, home):
        state = Path(home) / 'watchsmith'
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = state / 'delivery.sqlite3'
        # Create privately before SQLite opens it, without changing the process umask.
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        self.db = sqlite3.connect(path, timeout=5, isolation_level=None)
        self.db.execute('PRAGMA busy_timeout=5000')
        self.db.execute('''CREATE TABLE IF NOT EXISTS delivery (
            event_key TEXT PRIMARY KEY, state TEXT NOT NULL, owner TEXT NOT NULL,
            token TEXT NOT NULL, lease REAL NOT NULL, updated REAL NOT NULL,
            generic_attempted INTEGER NOT NULL DEFAULT 0)''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS summaries (
            reference TEXT PRIMARY KEY, thread TEXT NOT NULL, identity TEXT,
            payload TEXT NOT NULL, expires REAL NOT NULL, bound TEXT)''')

    def stage(self, thread_id, payload, turn_id=None, now=None):
        now = time.time() if now is None else now
        thread = event_key(thread_id, 'summary-thread')
        identity = event_key(thread_id, turn_id) if turn_id is not None else None
        if set(payload) - {'title', 'message', 'subtitle'} or not all(
                isinstance(payload.get(k), str) and payload[k].strip() and len(payload[k]) <= limit
                for k, limit in (('title', 100), ('message', 180))):
            raise ValueError('invalid reviewed notification')
        if 'subtitle' in payload and (not isinstance(payload['subtitle'], str) or len(payload['subtitle']) > 140):
            raise ValueError('invalid notification subtitle')
        reference = secrets.token_hex(24)
        self.db.execute('DELETE FROM summaries WHERE expires < ?', (now,))
        self.db.execute('INSERT INTO summaries VALUES (?,?,?,?,?,?)',
                        (reference, thread, identity, json.dumps(payload), now + SUMMARY_TTL, None))
        return {'queued': True, 'reference': reference, 'expires_in': SUMMARY_TTL,
                'final_marker': '<!-- watchsmith-result:' + reference + ' -->' if identity is None else None}

    def summary(self, event, now=None):
        """Resolve only an exact turn or an explicit reference in this final response."""
        now = time.time() if now is None else now
        try:
            thread = event_key(event.get('thread-id'), 'summary-thread')
        except ValueError:
            return None
        try:
            identity = event_key(event['thread-id'], event.get('turn-id'))
        except ValueError:
            identity = None
        message = event.get('last-assistant-message')
        match = MARKER.search(message) if isinstance(message, str) else None
        reference = match[1] if match else None
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if reference:
                rows = self.db.execute('SELECT reference,identity,payload,bound FROM summaries WHERE reference=? AND thread=? AND expires>=?', (reference, thread, now)).fetchall()
            elif identity:
                rows = self.db.execute('SELECT reference,identity,payload,bound FROM summaries WHERE identity=? AND thread=? AND expires>=?', (identity, thread, now)).fetchall()
            else:
                rows = []
            result = None
            if len(rows) == 1:
                ref, intended, payload, bound = rows[0]
                key = identity or event_key(event['thread-id'], 'summary-reference:' + ref)
                if (intended is None or intended == identity) and (bound is None or bound == key):
                    self.db.execute('UPDATE summaries SET bound=? WHERE reference=?', (key, ref))
                    result = (key, json.loads(payload))
            self.db.execute('COMMIT')
            return result
        except Exception:
            self.db.execute('ROLLBACK')
            raise

    def close(self):
        self.db.close()

    def claim(self, key, owner, lease=60, now=None):
        if owner not in ('detail', 'generic') or not 1 <= lease <= 120:
            raise ValueError('invalid claim owner or lease')
        now = time.time() if now is None else now
        db = self.db
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('DELETE FROM delivery WHERE updated < ? AND lease < ?', (now - RETENTION, now))
            row = db.execute('SELECT state,owner,token,lease,generic_attempted FROM delivery WHERE event_key=?', (key,)).fetchone()
            if row and row[0] == 'accepted':
                result = {'action': 'skip', 'reason': 'accepted'}
            elif row and row[0] == 'unknown':
                result = {'action': 'skip', 'reason': 'uncertain-delivery'}
            elif row and row[0] == 'pending' and row[3] > now:
                result = {'action': 'wait', 'retry_after': row[3] - now}
            elif row and row[4]:
                # One generic attempt, including ambiguous timeout. Never retry it blindly.
                result = {'action': 'skip', 'reason': 'generic-attempted'}
            elif row and owner == 'detail':
                result = {'action': 'skip', 'reason': 'previous-detail-attempt'}
            else:
                token = secrets.token_hex(24)
                db.execute('INSERT OR REPLACE INTO delivery VALUES (?,?,?,?,?,?,?)',
                           (key, 'pending', owner, token, now + lease, now, int(owner == 'generic')))
                result = {'action': 'send', 'token': token, 'correlation_tag': 'watchsmith-' + token}
            db.execute('COMMIT')
            return result
        except Exception:
            db.execute('ROLLBACK')
            raise

    def finish(self, key, token, outcome, now=None):
        if outcome not in ('accepted', 'failed', 'unknown'):
            raise ValueError('invalid outcome')
        now = time.time() if now is None else now
        cursor = self.db.execute('UPDATE delivery SET state=?, lease=0, updated=? WHERE event_key=? AND token=? AND state="pending"', (outcome, now, key, token))
        return cursor.rowcount == 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=installed_home())
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('claim', 'finish'):
        p = sub.add_parser(command)
        p.add_argument('--thread-id', required=True)
        p.add_argument('--turn-id', required=True)
        if command == 'claim':
            p.add_argument('--lease-seconds', type=int, default=60)
        else:
            p.add_argument('--token', required=True)
            p.add_argument('--outcome', choices=('accepted', 'failed', 'unknown'), required=True)
    args = parser.parse_args()
    store = None
    try:
        key = event_key(args.thread_id, args.turn_id)
        store = Store(args.home)
        if args.command == 'claim':
            result = store.claim(key, 'detail', args.lease_seconds)
        else:
            result = {'recorded': store.finish(key, args.token, args.outcome)}
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, sqlite3.Error):
        print('[watchsmith] coordination unavailable; keep generic fallback and do not guess event IDs', file=sys.stderr)
        return 2
    finally:
        if store:
            store.close()


if __name__ == '__main__':
    raise SystemExit(main())
