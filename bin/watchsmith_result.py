#!/usr/bin/env python3
"""Build reviewed notification arguments or queue them locally; never send or upload."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

FIELDS = ('summary', 'changes', 'verification', 'limitations', 'next_step')
STATUSES = {'completed', 'partial', 'blocked', 'failed'}
ALLOWED = {'schema_version', 'status', 'result_url', 'task_name', 'notification_summary', 'notification_verification', *FIELDS}
LABELS = {'completed': '완료', 'partial': '일부 완료', 'blocked': '확인 필요', 'failed': '실패'}


def validate(record):
    if not isinstance(record, dict) or set(record) - ALLOWED:
        raise ValueError('result must be an object containing only documented fields')
    if type(record.get('schema_version')) is not int or record['schema_version'] != 1:
        raise ValueError('schema_version must be 1')
    if not isinstance(record.get('status'), str) or record['status'] not in STATUSES:
        raise ValueError('unsupported status')
    for field in FIELDS:
        value = record.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 4000:
            raise ValueError(f'{field} must contain 1–4000 characters')
    if 'result_url' in record and not isinstance(record['result_url'], str):
        raise ValueError('result_url must be a string')
    for field, limit in (('task_name', 60), ('notification_summary', 180), ('notification_verification', 120)):
        if field in record:
            value = record[field]
            if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
                raise ValueError(f'{field} must be a short single-line string')
    return record


def validate_link(value):
    # Structural guard only: callers must review access control and sensitivity.
    if not value or len(value) > 2048 or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError('result_url must be a valid public HTTPS link')
    try:
        url = urlsplit(value)
        host = url.hostname
        port = url.port
    except ValueError:
        raise ValueError('result_url is malformed') from None
    if url.scheme != 'https' or not host or url.username is not None or url.password is not None:
        raise ValueError('result_url must be HTTPS without embedded credentials')
    if port not in (None, 443):
        raise ValueError('result_url must use the HTTPS port')
    if '.' not in host or host.endswith(('.local', '.localhost', '.internal', '.test', '.invalid')):
        raise ValueError('local result links are not supported')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError('private result links are not supported')
    return value


def build_payload(record, share_details=False, include_result_link=False, share_preview=False):
    record = validate(record)
    if include_result_link and not share_details:
        raise ValueError('result links require --share-details')
    payload = {'title': 'Codex 작업 결과', 'message': '작업 결과가 준비되었습니다. Codex에서 확인해 주세요.'}
    if share_preview:
        if not all(record.get(field) for field in ('task_name', 'notification_summary')):
            raise ValueError('notification preview requires task_name and notification_summary')
        payload.update(title=record['task_name'] + ' · ' + LABELS[record['status']],
                       message=record['notification_summary'])
        if record.get('notification_verification'):
            payload['subtitle'] = '검증: ' + record['notification_verification']
    if not share_details:
        return payload
    metadata = {'schema_version': 'watchsmith.result.v1', 'status': record['status']}
    metadata.update({field: record[field] for field in FIELDS})
    if len(json.dumps(metadata, ensure_ascii=False).encode('utf-8')) > 16 * 1024:
        raise ValueError('metadata exceeds 16 KB; shorten the reviewed result')
    payload['metadata'] = metadata
    if not share_preview:
        payload['message'] = '작업 결과 요약이 기록에 저장되었습니다.'
    if include_result_link:
        payload['redirection'] = validate_link(record.get('result_url'))
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result_file', type=Path)
    parser.add_argument('--share-preview', action='store_true', help='include reviewed task name and result summary on the Lock Screen')
    parser.add_argument('--share-details', action='store_true', help='include reviewed, user-authorized summaries in metadata')
    parser.add_argument('--include-result-link', action='store_true', help='also include a separately reviewed HTTPS result link')
    parser.add_argument('--queue-for-hook', action='store_true', help='stage reviewed preview for one completion hook; do not also send via MCP')
    parser.add_argument('--thread-id', default=os.environ.get('CODEX_THREAD_ID'))
    parser.add_argument('--turn-id', default=os.environ.get('CODEX_TURN_ID'))
    parser.add_argument('--home', type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    try:
        raw = args.result_file.read_bytes()
        if len(raw) > 128 * 1024:
            raise ValueError('result file exceeds 128 KB')
        record = json.loads(raw)
        payload = build_payload(record, args.share_details, args.include_result_link, args.share_preview)
    except (OSError, UnicodeError, ValueError) as exc:
        # Do not echo source text, secret values, or local filenames on error.
        detail = str(exc) if type(exc) is ValueError else 'unable to read a valid UTF-8 JSON result'
        print(f'[watchsmith] {detail}', file=sys.stderr)
        return 2
    if args.queue_for_hook:
        if not args.share_preview or args.share_details or args.include_result_link:
            print('[watchsmith] hook queue requires --share-preview only; metadata and links use the separate MCP path', file=sys.stderr)
            return 2
        from watchsmith_delivery import Store
        import sqlite3
        store = None
        try:
            store = Store(args.home)
            payload = store.stage(args.thread_id, payload, args.turn_id)
        except (OSError, ValueError, sqlite3.Error):
            print('[watchsmith] summary queue unavailable; do not guess identity', file=sys.stderr)
            return 2
        finally:
            if store:
                store.close()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
