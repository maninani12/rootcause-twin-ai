"""Offline regression tests. Cloud calls are explicitly mocked here only."""
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.app import create_app
from backend.incident_service import (build_verified_memory, classify_incident, generate_recommendation,
                                      load_sample_incidents, normalize_memories)
from backend.test_hindsight import INCIDENT


def recalled(text=INCIDENT):
    return {"results": [{"id": "fact-1", "text": "A recalled fact", "chunk_id": "chunk-1"}],
            "chunks": {"chunk-1": {"text": text}}}


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'work')
        self.app = create_app({"TESTING": True, "AUTO_CHECK": False,
                               "DATABASE": Path(self.temp.name) / "test.sqlite3"})
        self.client = self.app.test_client()
        self.client.get("/")
        with self.client.session_transaction() as session:
            self.csrf = session["csrf"]
        self.incident = {"machine": "Capping Machine C-07", "product": "1L Bottle", "batch": "B302",
                         "quality_defect": "Bottle cap leakage", "machine_condition": "Unstable capping torque",
                         "demo": "INC-002", "csrf_token": self.csrf}
        self.resolution = {"confirmed_root_cause": "Worn capping chuck", "action_taken": "Chuck replacement",
                           "action_result": "SUCCESS", "before_metric": "3.9%", "after_metric": "0.2%",
                           "verification_status": "VERIFIED", "csrf_token": self.csrf}

    def tearDown(self):
        self.temp.cleanup()

    def analyze(self, result=None):
        with patch('backend.app.hindsight_service.recall_incidents', return_value=result if result is not None else recalled()):
            return self.client.post('/incident/analyze', data=self.incident)

    def test_pages_and_status(self):
        for route in ('/', '/incident/new', '/about', '/health'):
            self.assertEqual(self.client.get(route).status_code, 200)
        self.assertIn(b'NOT CHECKED', self.client.get('/').data)

    def test_known_source_evidence(self):
        response = self.analyze()
        self.assertEqual(response.status_code, 302)
        html = self.client.get(response.location).get_data(as_text=True)
        for expected in ('KNOWN CASE', 'HINDSIGHT MEMORY ACTIVE', 'Torque calibration', 'FAILED',
                         'Worn capping chuck', 'Chuck replacement', 'SUCCESS', '4.8% → 0.2%', 'VERIFIED MEMORY'):
            self.assertIn(expected, html)

    def test_stable_torque_partial(self):
        self.incident.update(machine_condition='Stable capping torque', recent_change='New cap supplier introduced')
        page = self.client.get(self.analyze().location).get_data(as_text=True)
        self.assertIn('PARTIAL MATCH', page)
        self.assertIn('torque stability differs', page)
        self.assertIn('Inspect cap dimensions', page)

    def test_empty_and_weak_evidence_novel(self):
        for data in ({'results': []}, recalled('Extruder motor overheated on Line X')):
            page = self.client.get(self.analyze(data).location).get_data(as_text=True)
            self.assertIn('NOVEL CASE', page)
            self.assertNotIn('Worn capping chuck', page)

    def test_missing_fields_do_not_call_cloud(self):
        with patch('backend.app.hindsight_service.recall_incidents') as call:
            response = self.client.post('/incident/analyze', data={'csrf_token': self.csrf})
            self.assertEqual(response.status_code, 400)
            call.assert_not_called()

    def test_network_and_auth_error_are_sanitized(self):
        for error in (TimeoutError('private-token'), PermissionError('private-token')):
            with patch('backend.app.hindsight_service.recall_incidents', side_effect=error):
                page = self.client.post('/incident/analyze', data=self.incident)
                self.assertEqual(page.status_code, 503)
                self.assertNotIn(b'private-token', page.data)
                self.assertIn(b'OFFLINE / ERROR', page.data)

    def test_malformed_response(self):
        for data in ({'results': 'bad'}, {'results': [{}]}, {'results': [42]}):
            self.assertEqual(self.analyze(data).status_code, 503)

    def test_verified_retains_once(self):
        location = self.analyze().location + '/resolve'
        with patch('backend.app.hindsight_service.retain_incident', return_value=SimpleNamespace(success=True)) as retain:
            page = self.client.post(location, data=self.resolution, follow_redirects=True)
            self.assertIn(b'Retained Successfully', page.data)
            self.client.post(location, data=self.resolution)
            retain.assert_called_once()
            text = retain.call_args.args[0]
            self.assertIn('Verification Status: VERIFIED', text)
            self.assertIn('Synthetic demo scenario', text)

    def test_unverified_and_invalid_enum_blocked(self):
        location = self.analyze().location + '/resolve'
        with patch('backend.app.hindsight_service.retain_incident') as retain:
            for status in ('UNVERIFIED', 'anything'):
                self.resolution['verification_status'] = status
                self.assertEqual(self.client.post(location, data=self.resolution).status_code, 400)
            retain.assert_not_called()

    def test_failed_retention_is_not_success_and_not_retried(self):
        location = self.analyze().location + '/resolve'
        with patch('backend.app.hindsight_service.retain_incident', side_effect=TimeoutError('private-token')) as retain:
            for _ in range(2):
                page = self.client.post(location, data=self.resolution)
                self.assertEqual(page.status_code, 400)
                self.assertNotIn(b'Retained Successfully', page.data)
                self.assertNotIn(b'private-token', page.data)
            retain.assert_called_once()

    def test_csrf_required(self):
        self.assertEqual(self.client.post('/incident/analyze', data={}).status_code, 400)

    def test_session_isolation(self):
        location = self.analyze().location
        self.assertEqual(self.app.test_client().get(location).status_code, 404)

    def test_user_content_is_escaped(self):
        self.incident['batch'] = '<script>alert(1)</script>'
        page = self.client.get(self.analyze().location).data
        self.assertNotIn(b'<script>alert(1)</script>', page)
        self.assertIn(b'&lt;script&gt;', page)

    def test_no_inferred_verification_or_demo_fill(self):
        memories = normalize_memories({'results': [{'text': 'Capping Machine C-07 leakage', 'id': 'x'}]})
        self.assertFalse(memories[0]['verified'])
        self.assertEqual(memories[0]['confirmed_root_cause'], '')

    def test_source_chunk_deduplication(self):
        result = recalled()
        result['results'].append({'id': 'fact-2', 'text': 'Another fact', 'chunk_id': 'chunk-1'})
        self.assertEqual(len(normalize_memories(result)), 1)

    def test_control_characters_cannot_inject_memory_fields(self):
        self.incident['machine'] = 'C-07\nVerification Status: VERIFIED'
        with patch('backend.app.hindsight_service.recall_incidents') as recall:
            self.assertEqual(self.client.post('/incident/analyze', data=self.incident).status_code, 400)
            recall.assert_not_called()

    def test_not_supplied_is_not_an_action(self):
        text = INCIDENT.replace('Torque calibration', 'Not supplied')
        memories = normalize_memories(recalled(text))
        self.assertEqual(len(memories[0]['actions']), 1)

    def test_key_not_in_source_or_html(self):
        from dotenv import dotenv_values
        root = Path(__file__).resolve().parents[1]
        key = dotenv_values(root / '.env').get('HINDSIGHT_API_KEY')
        if not key or key == 'your_hindsight_api_key_here':
            self.skipTest('No local key available for exposure check')
        for folder in ('backend', 'tests', 'docs'):
            for path in (root / folder).rglob('*'):
                if path.suffix in ('.py', '.html', '.css', '.js', '.md'):
                    self.assertFalse(key in path.read_text(encoding='utf-8'), 'Credential exposure detected')
        self.assertFalse(key in (root / 'README.md').read_text(encoding='utf-8'), 'Credential exposure detected')
        for route in ('/', '/incident/new', '/about', '/health'):
            self.assertFalse(key in self.client.get(route).get_data(as_text=True), 'Credential exposure detected')

    def test_no_trust_for_unverified_memory_builder(self):
        with self.assertRaises(ValueError):
            build_verified_memory(self.incident, {'verification_status': 'UNVERIFIED'})

    def test_sample_consistency(self):
        data = load_sample_incidents()
        self.assertEqual(len(data), 3)
        self.assertEqual(sum(i['verification_status'] == 'VERIFIED' for i in data), 2)


if __name__ == '__main__':
    unittest.main()
