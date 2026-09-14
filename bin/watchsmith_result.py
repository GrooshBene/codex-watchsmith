#!/usr/bin/env python3
"""Build ActivitySmith MCP arguments locally; never send or upload anything."""
import argparse
import ipaddress
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

FIELDS = ('summary', 'changes', 'verification', 'limitations', 'next_step')
STATUSES = {'completed', 'partial', 'blocked', 'failed'}
ALLOWED = {'schema_version', 'status', 'result_url', *FIELDS}


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


def build_payload(record, share_details=False, include_result_link=False):
    record = validate(record)
    if include_result_link and not share_details:
        raise ValueError('result links require --share-details')
    payload = {'title': 'Codex 작업 결과', 'message': '작업 결과가 준비되었습니다. Codex에서 확인해 주세요.'}
    if not share_details:
        return payload
    metadata = {'schema_version': 'watchsmith.result.v1', 'status': record['status']}
    metadata.update({field: record[field] for field in FIELDS})
    if len(json.dumps(metadata, ensure_ascii=False).encode('utf-8')) > 16 * 1024:
        raise ValueError('metadata exceeds 16 KB; shorten the reviewed result')
    payload['metadata'] = metadata
    payload['message'] = '작업 결과 요약이 기록에 저장되었습니다.'
    if include_result_link:
        payload['redirection'] = validate_link(record.get('result_url'))
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result_file', type=Path)
    parser.add_argument('--share-details', action='store_true', help='include reviewed, user-authorized summaries in metadata')
    parser.add_argument('--include-result-link', action='store_true', help='also include a separately reviewed HTTPS result link')
    args = parser.parse_args()
    try:
        raw = args.result_file.read_bytes()
        if len(raw) > 128 * 1024:
            raise ValueError('result file exceeds 128 KB')
        record = json.loads(raw)
        payload = build_payload(record, args.share_details, args.include_result_link)
    except (OSError, UnicodeError, ValueError) as exc:
        # Do not echo source text, secret values, or local filenames on error.
        detail = str(exc) if type(exc) is ValueError else 'unable to read a valid UTF-8 JSON result'
        print(f'[watchsmith] {detail}', file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
