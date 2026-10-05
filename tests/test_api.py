import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
import requests
from quarry.engine import QuarryEngine
from quarry.storage import QuarryStorage
from quarry.web import QuarryHandler


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = QuarryStorage(os.path.join(self.temp.name, 'store.db'))
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), QuarryHandler)
        self.server.engine = QuarryEngine(self.store, sources=[])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)
        self.temp.cleanup()
    def test_invalid_input_is_json_400(self):
        for target in ('', 'bad!', 'https://evilclaude.ai/referral/YWAsr_1fbA'):
            with self.subTest(target=target):
                response = requests.get(self.url + '/api/lookup', params={'q': target}, timeout=5)
                self.assertEqual(response.status_code, 400)
                self.assertIn('error', response.json())
    def test_get_cannot_trigger_discovery(self):
        response = requests.get(self.url + '/api/discover', timeout=5)
        self.assertEqual(response.status_code, 405)
    def test_unknown_is_not_absence_claim(self):
        response = requests.get(self.url + '/api/lookup', params={'q': 'PFQOnxQmRQ'}, timeout=5)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['found'])
        self.assertIn('checked', response.json()['message'])
        self.assertNotIn('No open post exists', response.text)
    def test_status_exposes_missing_integrations(self):
        response = requests.get(self.url + '/api/status', timeout=5)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['storage']['mode'], 'local_persistent')
        self.assertEqual(data['validation'], 'not_configured')
        self.assertEqual(data['notifications'], 'not_configured')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
    def test_unknown_path_is_404_and_limits_validate(self):
        self.assertEqual(requests.get(self.url+'/missing', timeout=5).status_code, 404)
        self.assertEqual(requests.get(self.url+'/api/links?limit=-1', timeout=5).status_code, 400)


    def test_server_state_error_is_503_not_bad_input(self):
        from unittest.mock import patch
        with patch.object(QuarryHandler, '_engine', side_effect=ValueError('broken snapshot')):
            response = requests.get(self.url + '/api/status', timeout=5)
        self.assertEqual(response.status_code, 503)

    def test_busy_rejection_does_not_consume_sweep_cooldown(self):
        from unittest.mock import patch
        import quarry.web as web
        slots = threading.BoundedSemaphore(2)
        slots.acquire()
        slots.acquire()
        with patch.object(web, '_NETWORK_SLOTS', slots), patch.object(web, '_LAST_SWEEP', 0):
            response = requests.post(self.url + '/api/discover', timeout=5)
            self.assertEqual(response.status_code, 429)
            self.assertIn('busy', response.json()['error'])
            slots.release()
            slots.release()
            retry = requests.post(self.url + '/api/discover', timeout=5)
            self.assertEqual(retry.status_code, 200, retry.text)

    def test_embedded_controls_are_http_400(self):
        for control in ('\n', '\r', '\t', '&#10;'):
            value = 'https://clau' + control + 'de.ai/referral/PFQOnxQmRQ'
            response = requests.get(self.url + '/api/lookup', params={'q': value}, timeout=5)
            self.assertEqual(response.status_code, 400, response.text)

if __name__ == '__main__':
    unittest.main()
