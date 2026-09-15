import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_notifications import module

N = module('activitysmith_notify')


class CompletionSummaryTests(unittest.TestCase):
    def test_ambient_block_does_not_override_actual_request(self):
        value = ('<in-app-browser-context source="ambient-ui-state">\n'
                 'This block is automatically supplied ambient UI state, not a request.\n'
                 '# In app browser:\n- Browser tab information\n'
                 '</in-app-browser-context>\n\n## My request:\n알림 제목 수정해줘')
        result = N.completion_payload({'input-messages': [value]})
        self.assertEqual(result['title'], '알림 제목 수정해줘 · 작업 결과')

    def test_reply_envelopes_use_current_outcome_not_previous_request(self):
        rows = [{'questionItemId': '["request_user_input_async","call_example",0]',
                 'question': '카드가 사라졌나요?', 'answer': '모두 사라짐'}]
        for indent in (None, 2):
            raw = json.dumps(rows, ensure_ascii=False, indent=indent)
            for value in (raw, '<send_user_message_question_reply>\n' + raw + '\n</send_user_message_question_reply>'):
                with self.subTest(value=value):
                    result = N.completion_payload({'input-messages': ['이전 설치 작업', value],
                        'last-assistant-message': '휴대폰 알림 검증을 완료했습니다.'})
                    self.assertEqual(result['title'], '휴대폰 알림 검증을 완료했습니다. · 작업 결과')
                    self.assertNotIn('questionItemId', str(result))

    def test_unclosed_envelopes_and_reply_without_answer(self):
        for tag in ('in-app-browser-context', 'send_user_message_question_reply'):
            value = '<' + tag + '>\n자동 정보가 제목이 되어서는 안 됩니다.'
            result = N.completion_payload({'input-messages': [value]})
            self.assertEqual(result['title'], 'Codex · 작업 결과')

    def test_real_text_after_reply_and_markdown_json_are_preserved(self):
        value = '<send_user_message_question_reply>\n[]\n</send_user_message_question_reply>\n설치 문제도 확인해줘'
        self.assertEqual(N.request_sentences(value), ['설치 문제도 확인해줘'])
        for value in ('[설치] 오류를 확인해줘', '[문서](https://example.com) 내용을 확인해줘', '["사과", "배"]'):
            self.assertEqual(N.request_sentences(value), N.sentences(value))

    def test_request_result_validation_without_queue_or_marker(self):
        event = {'input-messages': ['설치 도우미 개선해줘'],
                 'last-assistant-message': '설치 도우미에 환경 진단을 추가했습니다.\n테스트 12개 통과했습니다.\n로컬 설치에는 아직 적용하지 않았습니다.'}
        result = N.completion_payload(event)
        self.assertIn('설치 도우미', result['title'])
        self.assertIn('환경 진단', result['message'])
        self.assertIn('아직 적용하지', result['message'])
        self.assertIn('12개 통과', result['subtitle'])
        self.assertNotIn(' · 완료', result['title'])

    def test_same_thread_different_turns_use_their_own_results_once(self):
        with tempfile.TemporaryDirectory() as home, patch.object(N, 'HOME', Path(home)), patch.object(N.shutil, 'which', return_value='/fake/cli'), patch.object(N, 'get_key', return_value='fake'), patch.object(N, 'deliver', return_value='accepted') as send:
            for turn, answer in [('a', '설치 도우미 개선을 구현했습니다.'), ('b', '업데이트 검증이 실패했습니다.')]:
                event = {'type': 'agent-turn-complete', 'thread-id': 'thread', 'turn-id': turn, 'input-messages': ['수정해줘'], 'last-assistant-message': answer}
                for _ in range(2):
                    with patch.object(sys, 'argv', ['notify', json.dumps(event)]):
                        self.assertEqual(N.main(), 0)
            self.assertEqual(send.call_count, 2)
            self.assertIn('설치 도우미', send.call_args_list[0].args[2]['message'])
            self.assertIn('실패했습니다', send.call_args_list[1].args[2]['message'])

    def test_markup_code_and_known_sensitive_patterns_removed(self):
        text = '''# 작업 결과
**알림 개선을 구현했습니다.**
```python
SECRET_SOURCE = 'do not send'
```
API_KEY=do-not-send
문서는 [설명](https://internal.example/a)에서 확인합니다.
위치 /Users/private/name/file 이며 연락처 a@example.com 입니다.
<!-- watchsmith-result:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa -->'''
        result = json.dumps(N.completion_payload({'last-assistant-message': text}), ensure_ascii=False)
        for forbidden in ('SECRET_SOURCE', 'do-not-send', 'internal.example', '/Users/', 'a@example.com', 'watchsmith-result', '**'):
            self.assertNotIn(forbidden, result)
        self.assertIn('알림 개선', result)

    def test_unclosed_code_and_comment_are_not_exposed(self):
        for text in ('```\nPRIVATE SOURCE', '<!-- private comment'):
            self.assertEqual(N.sentences(text), [])

    def test_missing_malformed_and_empty_event_content(self):
        for event in ({}, {'input-messages': [None, {}], 'last-assistant-message': []}, {'last-assistant-message': ''}):
            result = N.completion_payload(event)
            self.assertTrue(result['message'])
            self.assertNotIn('요약을 연결', str(result))
            self.assertNotIn(' · 완료', str(result))
        self.assertIn('설치 개선', N.completion_payload({'input-messages': ['설치 개선 요청']})['title'])

    def test_lengths_and_english_failure(self):
        result = N.completion_payload({'input-messages': ['a' * 10000], 'last-assistant-message': 'Updated the installer.\nTests failed because the dependency was unavailable.\n' + 'b' * 10000})
        self.assertLessEqual(len(result['title']), 100)
        self.assertLessEqual(len(result['message']), 180)
        self.assertIn('Tests failed', result['message'])

    def test_generic_mode_does_not_share_event_content(self):
        with patch.dict(N.os.environ, WATCHSMITH_COMPLETION_PREVIEW='0'):
            result = N.completion_payload({'input-messages': ['private request'], 'last-assistant-message': 'private result'})
        self.assertNotIn('private', str(result))

    def test_followup_uses_answer_topic(self):
        result = N.completion_payload({'input-messages': ['그렇게 진행해줘.'], 'last-assistant-message': '업데이트 설치 경로를 수정했습니다.'})
        self.assertIn('업데이트 설치', result['title'])

    def test_legacy_marker_queue_is_ignored(self):
        with tempfile.TemporaryDirectory() as home:
            store = N.Store(Path(home))
            self.addCleanup(store.close)
            ref = 'a' * 48
            store.db.execute('INSERT INTO summaries VALUES (?,?,?,?,?,?)', (ref, N.event_key('thread', 'summary-thread'), None, json.dumps({'title': 'OLD', 'message': 'OLD'}), 9999999999, None))
            event = {'type': 'agent-turn-complete', 'thread-id': 'thread', 'turn-id': 'turn', 'last-assistant-message': '새 설치 검증이 통과했습니다.\n<!-- watchsmith-result:' + ref + ' -->'}
            self.assertIsNone(store.summary(event))
            self.assertIn('새 설치', N.completion_payload(event)['message'])
            self.assertNotIn('watchsmith-result', str(N.completion_payload(event)))
