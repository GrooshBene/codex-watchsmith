import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_notifications import ROOT, module

RESULT = module('watchsmith_result')
CONFIG = module('watchsmith_config')
EXAMPLE = json.loads((ROOT / 'config/result-example.json').read_text())


class ResultTests(unittest.TestCase):
    def test_default_does_not_include_details_or_link(self):
        record = dict(EXAMPLE, result_url='https://example.com/private-result')
        payload = RESULT.build_payload(record)
        self.assertEqual(set(payload), {'title', 'message'})
        self.assertNotIn(record['summary'], json.dumps(payload, ensure_ascii=False))

    def test_explicit_metadata_and_line_breaks(self):
        record = dict(EXAMPLE, changes='첫 항목\nSecond item')
        payload = RESULT.build_payload(record, share_details=True)
        self.assertEqual(payload['metadata']['changes'], record['changes'])
        self.assertEqual(payload['metadata']['status'], 'partial')
        self.assertNotIn('payload', payload)
        self.assertNotIn('redirection', payload)

    def test_preview_is_explicit_and_independent_of_metadata(self):
        record = dict(EXAMPLE, task_name='업데이터 수정', notification_summary='Python 전달 수정. 검증 통과.')
        self.assertNotIn(record['task_name'], json.dumps(RESULT.build_payload(record), ensure_ascii=False))
        for state, label in RESULT.LABELS.items():
            for details in (False, True):
                payload = RESULT.build_payload(dict(record, status=state), share_details=details, share_preview=True)
                self.assertEqual(payload['title'], '업데이터 수정 · ' + label)
                self.assertEqual(payload['message'], record['notification_summary'])
                self.assertEqual('metadata' in payload, details)
        with self.assertRaises(ValueError):
            RESULT.build_payload({k: v for k, v in EXAMPLE.items() if k not in ('task_name', 'notification_summary')}, share_preview=True)
        with self.assertRaises(ValueError):
            RESULT.build_payload(dict(record, task_name='bad\nline'), share_preview=True)
        with self.assertRaises(ValueError):
            RESULT.build_payload(dict(record, notification_summary='a' * 181), share_preview=True)

    def test_links_need_separate_opt_in(self):
        record = dict(EXAMPLE, result_url='https://example.com/report')
        self.assertNotIn('redirection', RESULT.build_payload(record, True))
        self.assertEqual(RESULT.build_payload(record, True, True)['redirection'], record['result_url'])
        with self.assertRaises(ValueError):
            RESULT.build_payload(record, False, True)

    def test_reject_local_or_credentialed_links(self):
        for url in ['file:///tmp/result', 'http://example.com', 'https://localhost/a', 'https://127.0.0.1/a', 'https://10.0.0.1/a', 'https://[::1]/a', 'https://host.internal/a', 'https://user:secret@example.com', 'https://example.com:secret/a', '', None]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                RESULT.build_payload(dict(EXAMPLE, result_url=url), True, True)

    def test_reject_unknown_fields_and_invalid_types(self):
        cases = [[], dict(EXAMPLE, raw_log='PRIVATE'), dict(EXAMPLE, schema_version=True), dict(EXAMPLE, status=[]), dict(EXAMPLE, status='unknown'), dict(EXAMPLE, changes=['one']), dict(EXAMPLE, limitations=' ')]
        for record in cases:
            with self.subTest(record=record), self.assertRaises(ValueError):
                RESULT.build_payload(record, True)

    def test_limits_count_unicode_bytes_and_do_not_truncate(self):
        with self.assertRaises(ValueError):
            RESULT.build_payload(dict(EXAMPLE, changes='a' * 4001), True)
        record = dict(EXAMPLE)
        record.update({field: '한' * 1500 for field in RESULT.FIELDS})
        with self.assertRaises(ValueError):
            RESULT.build_payload(record, True)

    def test_queue_cli_stages_preview_and_requires_explicit_sharing(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'result.json'
            source.write_text(json.dumps(dict(EXAMPLE, task_name='작업', notification_summary='검증 완료', notification_verification='5개 통과')))
            args = [sys.executable, str(ROOT / 'bin/watchsmith_result.py'), str(source),
                    '--queue-for-hook', '--home', directory, '--thread-id', 'thread']
            rejected = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(rejected.returncode, 2)
            self.assertFalse((Path(directory) / 'watchsmith').exists())
            result = subprocess.run(args + ['--share-preview'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            staged = json.loads(result.stdout)
            self.assertTrue(staged['queued'])
            self.assertIn('watchsmith-result:', staged['final_marker'])
            self.assertNotIn('검증 완료', result.stdout)

    def test_cli_is_local_and_errors_do_not_echo_content(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'result.json'
            source.write_text(json.dumps(EXAMPLE))
            p = subprocess.run([sys.executable, str(ROOT / 'bin/watchsmith_result.py'), str(source), '--share-details'], capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(p.stdout)['metadata']['status'], 'partial')
            source.write_text('{"PRIVATE_SECRET":')
            p = subprocess.run([sys.executable, str(ROOT / 'bin/watchsmith_result.py'), str(source)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 2)
            self.assertEqual(p.stdout, '')
            self.assertNotIn('PRIVATE_SECRET', p.stderr)


class PolicyTests(unittest.TestCase):
    def test_update_preserves_outside_text_and_backs_up_once(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            old = 'Personal preference\n' + CONFIG.POLICY_BEGIN + '\nold policy\n' + CONFIG.POLICY_END + '\nOther instructions\n'
            (home / 'AGENTS.md').write_text(old)
            CONFIG.install_policy(home)
            updated = (home / 'AGENTS.md').read_text()
            self.assertTrue(updated.startswith('Personal preference\n'))
            self.assertTrue(updated.endswith('\nOther instructions\n'))
            self.assertIn('watchsmith_result.py', updated)
            backups = list((home / 'watchsmith').glob('AGENTS.md.backup.*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), old)
            CONFIG.install_policy(home)
            self.assertEqual(len(list((home / 'watchsmith').glob('AGENTS.md.backup.*'))), 1)

    def test_bad_markers_stop_install_before_notify_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / 'config.toml').write_text('notify = ["original"]\n')
            for bad in [CONFIG.POLICY_BEGIN, CONFIG.POLICY_END, CONFIG.POLICY_END + CONFIG.POLICY_BEGIN, CONFIG.POLICY_BEGIN * 2 + CONFIG.POLICY_END]:
                (home / 'AGENTS.md').write_text(bad)
                p = subprocess.run([sys.executable, str(ROOT / 'bin/watchsmith_config.py'), 'install', str(home)], capture_output=True)
                self.assertNotEqual(p.returncode, 0)
                self.assertEqual((home / 'config.toml').read_text(), 'notify = ["original"]\n')
                self.assertEqual((home / 'AGENTS.md').read_text(), bad)
                self.assertFalse((home / 'watchsmith').exists())


class LegacyPolicyTests(unittest.TestCase):
    def test_legacy_replaced_and_personal_content_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            original = 'Personal before\n<!-- BEGIN activitysmith autonomous workflow -->\nold policy\n<!-- END activitysmith autonomous workflow -->\nMusic instructions\n'
            (home / 'AGENTS.md').write_text(original)
            before, after = CONFIG.policy_text(home)
            self.assertEqual(before, original)
            self.assertTrue(after.startswith('Personal before\n'))
            self.assertTrue(after.endswith('\nMusic instructions\n'))
            self.assertNotIn('activitysmith autonomous workflow', after)
            self.assertEqual(after.count(CONFIG.POLICY_BEGIN), 1)

    def test_mixed_or_malformed_legacy_policy_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            for text in ('<!-- BEGIN activitysmith autonomous workflow -->',
                         '<!-- BEGIN activitysmith autonomous workflow --><!-- END activitysmith autonomous workflow -->' + CONFIG.POLICY_BEGIN + CONFIG.POLICY_END):
                (home / 'AGENTS.md').write_text(text)
                with self.assertRaises(ValueError):
                    CONFIG.policy_text(home)
