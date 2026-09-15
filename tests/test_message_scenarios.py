import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_notifications import ROOT, module

R = module('watchsmith_result')


class ScenarioTests(unittest.TestCase):
    def record(self, name):
        role = R.SCENARIOS[name][0]
        data = {'task_name': '알림 개선', 'summary': '현재 단계에서 확인한 수행 내용입니다.'}
        if role == 'live':
            data['stream_key'] = 'test-run'
            kind = R.SCENARIOS[name][2]
            if kind == 'progress':
                data['percentage'] = 25
            elif kind == 'segmented_progress':
                data.update(current_step=1, number_of_steps=3)
            elif kind in ('stats', 'metrics'):
                data['metrics'] = [{'label': '처리 건수', 'value': 12}]
        elif role == 'approval':
            data.update(execution_context={'tool': 'shell', 'command': 'git diff --check'}, scope={'type': 'repository', 'value': 'example'})
        return data

    def test_every_scenario_builds_a_bounded_message(self):
        self.assertEqual(len(R.SCENARIOS), 29)
        for name, spec in R.SCENARIOS.items():
            with self.subTest(name=name):
                result = R.build_scenario(name, self.record(name))
                self.assertEqual(result['scenario'], name)
                self.assertNotIn('final_marker', result)
                if spec[0] == 'terminal':
                    self.assertEqual(result['route'], 'completion_hook')
                    self.assertNotIn('tool', result)
                elif spec[0] == 'approval':
                    self.assertEqual(result['tool'], 'request_approval')
                    self.assertNotEqual(result['arguments']['approve_label'], result['arguments']['reject_label'])
                else:
                    state = result['arguments']['content_state']
                    self.assertEqual(state['type'], spec[2])
                    self.assertEqual(state['icon'], spec[4])

    def test_unknown_progress_uses_timer(self):
        for name in ('implementation', 'download', 'tests'):
            result = R.build_scenario(name, {'task_name': '테스트', 'summary': '실행 중', 'stream_key': 'stable'})
            state = result['arguments']['content_state']
            self.assertEqual(state['type'], 'timer')
            self.assertFalse(state['counts_down'])
            self.assertNotIn('percentage', state)

    def test_explicit_type_keeps_timer_origin(self):
        record = self.record('implementation')
        record.pop('current_step'); record.pop('number_of_steps')
        record.update(activity_type='timer', timer_start_at='2026-09-15T06:00:00Z')
        state = R.build_scenario('implementation', record)['arguments']['content_state']
        self.assertEqual(state['timer_start_at'], record['timer_start_at'])
        self.assertEqual(state['type'], 'timer')

    def test_rejects_bad_measurements_and_scope(self):
        invalid = [('tests', {'percentage': 101}), ('tests', {'percentage': True}),
                   ('tests', {'percentage': float('nan')}), ('measurement', {'metrics': []}),
                   ('implementation', {'current_step': 5}), ('analysis', {'stream_key': '../other'}),
                   ('analysis', {'activity_type': []}), ('approve_commit', {'scope': {}}),
                   ('approve_commit', {'execution_context': {'tool': 'shell'}}),
                   ('approve_commit', {'execution_context': {'tool': 'shell', 'arguments': {'value': float('nan')}}})]
        for name, changes in invalid:
            with self.subTest(name=name, changes=changes):
                with self.assertRaises(ValueError):
                    R.build_scenario(name, dict(self.record(name), **changes))

    def test_unknown_fields_and_mixed_measurements_fail(self):
        with self.assertRaises(ValueError):
            R.build_scenario('analysis', dict(self.record('analysis'), percentage=12))
        with self.assertRaises(ValueError):
            R.build_scenario('completed', dict(self.record('completed'), command='anything'))
        with self.assertRaises(ValueError):
            R.build_scenario('missing', {})

    def test_approval_preserves_exact_command_and_scope(self):
        data = self.record('approve_commit')
        data['execution_context']['command'] = 'git commit -m "fix: keep spaces"'
        result = R.build_scenario('approve_commit', data)['arguments']
        self.assertEqual(result['execution_context'], data['execution_context'])
        self.assertEqual(result['scope'], data['scope'])
        self.assertEqual(result['approve_label'], '커밋 진행')
        self.assertEqual(result['reject_label'], '여기서 종료')

    def test_wrapper_approval_prefers_visible_live_buttons(self):
        with patch.dict(os.environ, WATCHSMITH_PROGRESS_CONTEXT='/private/context'):
            result = R.build_scenario('approve_commit', self.record('approve_commit'))
        self.assertEqual(result['arguments']['delivery'], 'live_activity')
        self.assertNotIn('stream_key', result['arguments'])

    def test_terminal_status_does_not_convert_cancellation_to_success(self):
        for name in ('partial', 'failed', 'cancelled', 'expired'):
            result = R.build_scenario(name, self.record(name))
            self.assertNotEqual(result['status'], 'completed')
            self.assertEqual(result['route'], 'completion_hook')

    def test_cli_is_local_and_requires_reviewed_sharing(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.json'
            source.write_text(json.dumps(self.record('approve_commit')))
            command = [sys.executable, str(ROOT / 'bin/watchsmith_result.py'), str(source), '--scenario', 'approve_commit']
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn('git diff', result.stderr)
            result = subprocess.run(command + ['--share-preview'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['tool'], 'request_approval')
            result = subprocess.run(command + ['--share-preview', '--queue-for-hook'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ['input.json'])

    def test_cli_lists_catalog_without_input(self):
        result = subprocess.run([sys.executable, str(ROOT / 'bin/watchsmith_result.py'), '--list-scenarios'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(set(json.loads(result.stdout)), set(R.SCENARIOS))

    def test_explicit_push_or_auto_includes_long_press_hint(self):
        for delivery in ('push_notification', 'auto'):
            record = dict(self.record('approve_commit'), delivery=delivery)
            result = R.build_scenario('approve_commit', record)['arguments']
            self.assertEqual(result['delivery'], delivery)
            self.assertIn('길게 눌러', result['details'])

    def test_live_default_does_not_require_hidden_gesture(self):
        result = R.build_scenario('approve_commit', self.record('approve_commit'))['arguments']
        self.assertEqual(result['delivery'], 'live_activity')
        self.assertNotIn('길게 눌러', result['details'])
