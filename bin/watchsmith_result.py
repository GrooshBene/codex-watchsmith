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


# Stable scenario IDs; wording describes state, never fabricates measurements.
SCENARIOS = {
    'analysis': ('live', '분석 중', 'timer', 'blue', 'magnifyingglass'),
    'planning': ('live', '계획 수립', 'timer', 'blue', 'list.bullet'),
    'implementation': ('live', '구현 중', 'segmented_progress', 'blue', 'hammer'),
    'validation': ('live', '검증 중', 'segmented_progress', 'blue', 'checkmark.shield'),
    'tests': ('live', '테스트 실행', 'progress', 'blue', 'checklist'),
    'build': ('live', '빌드 중', 'timer', 'blue', 'gearshape.2'),
    'download': ('live', '다운로드 중', 'progress', 'blue', 'arrow.down.circle'),
    'upload': ('live', '업로드 중', 'progress', 'blue', 'arrow.up.circle'),
    'installation': ('live', '설치 중', 'segmented_progress', 'blue', 'shippingbox'),
    'deployment': ('live', '배포 중', 'segmented_progress', 'blue', 'paperplane'),
    'retrying': ('live', '재시도 중', 'timer', 'orange', 'arrow.clockwise'),
    'recovery': ('live', '복구 중', 'segmented_progress', 'orange', 'wrench.and.screwdriver'),
    'measurement': ('live', '측정 중', 'metrics', 'blue', 'chart.bar'),
    'statistics': ('live', '처리 현황', 'stats', 'blue', 'number'),
    'blocked': ('live', '작업 중단', 'alert', 'orange', 'exclamationmark.circle'),
    'authentication': ('live', '인증 확인 필요', 'alert', 'orange', 'lock'),
    'failure': ('live', '오류 발생', 'alert', 'red', 'xmark.octagon'),
    'approve_validation': ('approval', '검증 진행', '검증을 진행할까요?', '검증 진행', '여기서 종료'),
    'approve_commit': ('approval', '커밋 진행', '확인한 변경사항을 커밋할까요?', '커밋 진행', '여기서 종료'),
    'approve_push': ('approval', '푸시 진행', '확인한 커밋을 원격 저장소에 푸시할까요?', '푸시 진행', '로컬에 유지'),
    'approve_release': ('approval', '릴리즈 발행', '확인한 버전을 릴리즈할까요?', '릴리즈 발행', '발행 보류'),
    'approve_retry': ('approval', '재시도 선택', '실패한 작업을 다시 시도할까요?', '재시도', '중단'),
    'approve_alternative': ('approval', '대안 선택', '설명한 대체 방법으로 진행할까요?', '대안으로 진행', '중단'),
    'approve_resume': ('approval', '작업 재개', '현재 상태를 확인한 작업을 재개할까요?', '재개', '중단'),
    'completed': ('terminal', '완료', 'completed'),
    'partial': ('terminal', '일부 완료', 'partial'),
    'failed': ('terminal', '실패', 'failed'),
    'cancelled': ('terminal', '사용자 선택으로 중단', 'partial'),
    'expired': ('terminal', '응답 기한 만료', 'blocked'),
}


def build_scenario(name, record):
    """Prepare existing MCP arguments; no transport, queue, approval or execution."""
    if name not in SCENARIOS or not isinstance(record, dict):
        raise ValueError('unknown scenario or invalid scenario record')
    spec = SCENARIOS[name]
    role, label = spec[:2]
    allowed = {'task_name', 'summary'}
    if role == 'live':
        allowed |= {'stream_key', 'activity_type', 'percentage', 'current_step', 'number_of_steps', 'metrics', 'timer_start_at'}
    elif role == 'approval':
        allowed |= {'execution_context', 'scope', 'delivery'}
    else:
        allowed |= {'verification'}
    if set(record) - allowed:
        raise ValueError('unexpected scenario fields')
    def short(field, limit):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
            raise ValueError('scenario requires bounded single-line ' + field)
        return value
    task, summary = short('task_name', 60), short('summary', 180)
    if role == 'terminal':
        preview = {'title': task + ' · ' + label, 'message': summary}
        if 'verification' in record:
            preview['subtitle'] = '검증: ' + short('verification', 120)
        return {'scenario': name, 'route': 'completion_hook', 'status': spec[2], 'preview': preview,
                'instruction': 'Use this wording in the final answer; do not send another completion Push. Exact-ID reviewed queues remain optional.'}
    if role == 'approval':
        context, scope = record.get('execution_context'), record.get('scope')
        if not isinstance(context, dict) or set(context) - {'tool', 'command', 'arguments'}:
            raise ValueError('approval requires an exact execution_context')
        if not isinstance(context.get('tool'), str) or not context['tool'].strip() or len(context['tool']) > 120:
            raise ValueError('approval requires a bounded operation name')
        if not context.get('command') and not context.get('arguments'):
            raise ValueError('approval requires concrete command or tool arguments')
        if 'command' in context and (not isinstance(context['command'], str) or not context['command'].strip() or len(context['command']) > 4000):
            raise ValueError('invalid approval command')
        if 'arguments' in context and not isinstance(context['arguments'], dict):
            raise ValueError('invalid approval arguments')
        scope_types = {'working_directory', 'repository', 'project', 'environment', 'customer', 'account', 'resource'}
        if not isinstance(scope, dict) or set(scope) != {'type', 'value'} or not isinstance(scope.get('type'), str) or scope['type'] not in scope_types:
            raise ValueError('approval requires an exact scope')
        if not isinstance(scope['value'], str) or not scope['value'].strip() or len(scope['value']) > 1024:
            raise ValueError('invalid approval scope')
        try:
            size = len(json.dumps(context, allow_nan=False).encode())
        except (TypeError, ValueError):
            raise ValueError('invalid approval context') from None
        if size > 8192:
            raise ValueError('approval context is too large')
        delivery = record.get('delivery', 'live_activity')
        if delivery not in ('auto', 'live_activity', 'push_notification'):
            raise ValueError('invalid approval delivery')
        details = summary
        if delivery in ('auto', 'push_notification'):
            details += '\nPush 알림은 길게 눌러 선택하세요.'
        return {'scenario': name, 'route': 'approval', 'tool': 'request_approval', 'arguments': {
            'question': task + ' · ' + spec[2], 'details': details,
            'approve_label': spec[3], 'reject_label': spec[4], 'delivery': delivery,
            'appearance': {'color': 'orange', 'icon': {'symbol': 'questionmark.circle'}, 'badge': {'title': label}},
            'execution_context': context, 'scope': scope}}
    from watchsmith_progress import content
    import re
    key = record.get('stream_key')
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', key):
        raise ValueError('live scenario requires a stable stream_key')
    kind = record.get('activity_type', spec[2])
    # Unknown totals are elapsed time, never fabricated percentages or steps.
    if 'activity_type' not in record and ((kind == 'progress' and 'percentage' not in record) or
            (kind == 'segmented_progress' and not {'current_step', 'number_of_steps'} <= record.keys())):
        kind = 'timer'
    state = {'type': kind, 'title': task + ' · ' + label, 'subtitle': summary,
             'color': spec[3], 'icon': spec[4]}
    fields = {'progress': {'percentage'}, 'segmented_progress': {'current_step', 'number_of_steps'},
              'timer': {'timer_start_at'}, 'stats': {'metrics'}, 'metrics': {'metrics'}, 'alert': set()}
    if not isinstance(kind, str) or kind not in fields:
        raise ValueError('unsupported scenario activity type')
    measurements = {'percentage', 'current_step', 'number_of_steps', 'metrics', 'timer_start_at'}
    if (record.keys() & measurements) - fields[kind]:
        raise ValueError('measurement fields do not match activity type')
    state.update({k: record[k] for k in fields[kind] if k in record})
    if kind == 'alert':
        state['message'] = summary
    if kind in ('alert', 'progress', 'segmented_progress'):
        state['badge'] = {'title': label, 'color': spec[3]}
    try:
        state = content(state)
    except (TypeError, ValueError, OverflowError):
        raise ValueError('invalid or missing measured display values') from None
    return {'scenario': name, 'route': 'live_activity', 'tool': 'set_live_activity_stream',
            'arguments': {'stream_key': key, 'content_state': state}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result_file', type=Path, nargs='?')
    parser.add_argument('--list-scenarios', action='store_true', help='list local message scenarios')
    parser.add_argument('--scenario', choices=sorted(SCENARIOS), help='prepare reviewed scenario arguments without sending')
    parser.add_argument('--share-preview', action='store_true', help='include reviewed task name and result summary on the Lock Screen')
    parser.add_argument('--share-details', action='store_true', help='include reviewed, user-authorized summaries in metadata')
    parser.add_argument('--include-result-link', action='store_true', help='also include a separately reviewed HTTPS result link')
    parser.add_argument('--queue-for-hook', action='store_true', help='stage reviewed preview for one completion hook; do not also send via MCP')
    parser.add_argument('--thread-id', default=os.environ.get('CODEX_THREAD_ID'))
    parser.add_argument('--turn-id', default=os.environ.get('CODEX_TURN_ID'))
    parser.add_argument('--home', type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    if args.list_scenarios:
        if args.result_file or args.scenario or args.queue_for_hook or args.share_preview or args.share_details or args.include_result_link:
            parser.error('--list-scenarios cannot be combined with other output modes')
        print(json.dumps({k: {'route': v[0], 'label': v[1]} for k, v in SCENARIOS.items()}, ensure_ascii=False, indent=2))
        return 0
    if args.result_file is None:
        parser.error('a result file is required')
    if args.scenario and (not args.share_preview or args.share_details or args.include_result_link or args.queue_for_hook):
        parser.error('scenarios require --share-preview and cannot queue, include metadata or links')
    try:
        raw = args.result_file.read_bytes()
        if len(raw) > 128 * 1024:
            raise ValueError('result file exceeds 128 KB')
        record = json.loads(raw)
        payload = build_scenario(args.scenario, record) if args.scenario else build_payload(record, args.share_details, args.include_result_link, args.share_preview)
    except (OSError, UnicodeError, ValueError) as exc:
        # Do not echo source text, secret values, or local filenames on error.
        detail = str(exc) if type(exc) is ValueError else 'unable to read a valid UTF-8 JSON result'
        print(f'[watchsmith] {detail}', file=sys.stderr)
        return 2
    if args.queue_for_hook:
        if not args.share_preview or args.share_details or args.include_result_link:
            print('[watchsmith] hook queue requires --share-preview only; metadata and links use the separate MCP path', file=sys.stderr)
            return 2
        if not args.thread_id or not args.turn_id:
            print('[watchsmith] exact thread and turn IDs required for an optional preview; the hook summarizes the completion event automatically', file=sys.stderr)
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
