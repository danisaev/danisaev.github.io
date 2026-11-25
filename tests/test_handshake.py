import base64
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from app import ANIMATION_MS, START_DELAY_MS, create_app


API = '/handshake/api'
CSRF = {'X-CSRF-Token': 'test-csrf'}


class HandshakeTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.app = create_app({
            'TESTING': True,
            'DATABASE': Path(directory) / 'test.sqlite3',
            'OWNER_YANDEX_ID': '100',
            'YANDEX_CLIENT_ID': 'test-client',
            'YANDEX_CLIENT_SECRET': 'test-secret',
            'YANDEX_REDIRECT_URI': 'http://localhost/handshake/callback',
        })
        self.clock = self.enterContext(patch('app.now_ms', return_value=10_000))
        self.owner = self.signed_in('100', 'Даниил')
        self.guest = self.signed_in('200', 'Саша')
        self.other_guest = self.signed_in('300', 'Маша')

    def signed_in(self, user_id, name):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session.update(user_id=user_id, guest_name=name, csrf_token=CSRF['X-CSRF-Token'])
        return client

    def test_only_the_selected_guest_receives_the_shared_start_time(self):
        requested = self.guest.post(f'{API}/request', headers=CSRF).json['current']
        duplicate = self.guest.post(f'{API}/request', headers=CSRF).json['current']
        other = self.other_guest.post(f'{API}/request', headers=CSRF).json['current']
        self.assertEqual(requested, duplicate)
        self.assertEqual(len(self.owner.get(f'{API}/status').json['pending']), 2)

        accept = f'{API}/{requested["id"]}/accept'
        accepted = self.owner.post(accept, headers=CSRF).json
        result = accepted['current']
        self.assertEqual(result['starts_at'], 10_000 + START_DELAY_MS)
        self.assertEqual(accepted['pending'], [other])
        self.assertEqual(self.guest.get(f'{API}/status').json['current'], result)
        self.assertEqual(self.other_guest.get(f'{API}/status').json['current'], other)

        self.clock.return_value += 500
        self.assertEqual(self.owner.post(accept, headers=CSRF).json['current'], result)
        self.assertEqual(self.guest.post(f'{API}/request', headers=CSRF).json['current'], result)
        other_accept = f'{API}/{other["id"]}/accept'
        self.assertEqual(self.owner.post(other_accept, headers=CSRF).json['pending'], [other])

        self.clock.return_value = result['starts_at'] + ANIMATION_MS
        new_request = self.guest.post(f'{API}/request', headers=CSRF).json['current']
        self.assertNotEqual(new_request['id'], requested['id'])
        self.assertIsNone(new_request['starts_at'])
        self.assertIsNone(self.owner.post(accept, headers=CSRF).json['current'])
        self.assertEqual(self.owner.post(other_accept, headers=CSRF).json['current']['id'], other['id'])

    def test_sign_in_csrf_and_owner_permissions(self):
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.get(f'{API}/status').status_code, 401)
        self.assertEqual(self.guest.post(f'{API}/request').status_code, 403)
        self.assertEqual(self.owner.post(f'{API}/request', headers=CSRF).status_code, 403)
        request_id = self.guest.post(f'{API}/request', headers=CSRF).json['current']['id']
        self.assertEqual(self.guest.post(f'{API}/{request_id}/accept', headers=CSRF).status_code, 403)
        self.assertEqual(self.guest.post('/handshake/logout').status_code, 403)
        self.assertEqual(self.guest.post('/handshake/logout', data={'csrf_token': 'test-csrf'}).status_code, 303)
        self.assertEqual(self.guest.get(f'{API}/status').status_code, 401)

    def test_oauth_exchanges_code_with_pkce_and_loads_the_owner_role(self):
        client = self.app.test_client()
        login = client.get('/handshake/login')
        params = parse_qs(urlsplit(login.location).query)
        self.assertEqual(params['scope'], ['login:info'])
        self.assertEqual(params['code_challenge_method'], ['S256'])
        with patch('app.requests.post') as exchange, patch('app.requests.get') as profile:
            exchange.return_value.json.return_value = {'access_token': 'test-token'}
            profile.return_value.json.return_value = {'id': '100', 'first_name': 'Даниил'}
            callback = client.get('/handshake/callback', query_string={'state': params['state'][0], 'code': 'test'})
            verifier = exchange.call_args.kwargs['data']['code_verifier']
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=')
            self.assertEqual(params['code_challenge'], [challenge.decode()])
            self.assertEqual(profile.call_args.kwargs['headers'], {'Authorization': 'OAuth test-token'})
        self.assertEqual(callback.location, '/handshake')
        self.assertEqual(client.get(f'{API}/status').json['pending'], [])
        with client.session_transaction() as session:
            self.assertNotIn('access_token', session)
            self.assertNotIn('oauth', session)

    def test_invalid_oauth_state_never_calls_yandex(self):
        client = self.app.test_client()
        client.get('/handshake/login')
        with patch('app.requests.post') as exchange:
            callback = client.get('/handshake/callback?state=bad&code=test')
            exchange.assert_not_called()
        self.assertEqual(callback.location, '/handshake?login=failed')


if __name__ == '__main__':
    unittest.main()
