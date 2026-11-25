import base64
import hashlib
import os
import secrets
import sqlite3
import time
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

import requests
from flask import (
    Flask, jsonify, redirect, render_template, request, send_from_directory,
    session, url_for,
)


ROOT = Path(__file__).resolve().parent
START_DELAY_MS = 3000
ANIMATION_MS = 1100


def now_ms():
    return time.time_ns() // 1_000_000


def create_app(config=None):
    app = Flask(__name__, static_folder=None)
    public_url = os.environ.get('RENDER_EXTERNAL_URL', '').rstrip('/')
    redirect_uri = os.environ.get('YANDEX_REDIRECT_URI', '')
    if not redirect_uri and public_url:
        redirect_uri = f'{public_url}/handshake/callback'
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY') or secrets.token_hex(32),
        SESSION_COOKIE_SECURE=redirect_uri.startswith('https://'),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_REFRESH_EACH_REQUEST=False,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        YANDEX_CLIENT_ID=os.environ.get('YANDEX_CLIENT_ID', ''),
        YANDEX_CLIENT_SECRET=os.environ.get('YANDEX_CLIENT_SECRET', ''),
        YANDEX_REDIRECT_URI=redirect_uri,
        OWNER_YANDEX_ID=os.environ.get('OWNER_YANDEX_ID', ''),
        DATABASE=os.environ.get('HANDSHAKE_DATABASE', Path(app.instance_path) / 'handshakes.sqlite3'),
    )
    if config:
        app.config.update(config)
    if os.environ.get('RENDER') and not os.environ.get('SECRET_KEY'):
        raise RuntimeError('Set SECRET_KEY in the Render environment.')

    def connect_db():
        path = Path(app.config['DATABASE'])
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        db.execute('''
            CREATE TABLE IF NOT EXISTS handshakes (
                id TEXT PRIMARY KEY,
                guest_id TEXT NOT NULL UNIQUE,
                guest_name TEXT NOT NULL,
                requested_at INTEGER NOT NULL,
                starts_at INTEGER
            )
        ''')
        return db

    def is_owner():
        return bool(session.get('user_id') and session['user_id'] == app.config['OWNER_YANDEX_ID'])

    def oauth_ready():
        return all(app.config[key] for key in (
            'YANDEX_CLIENT_ID', 'YANDEX_CLIENT_SECRET', 'YANDEX_REDIRECT_URI',
        ))

    def same_token(expected, supplied):
        return bool(expected and supplied and secrets.compare_digest(expected.encode(), supplied.encode()))

    def serialize(row):
        return dict(row) if row else None

    def status(db):
        columns = 'id, guest_name, starts_at'
        if is_owner():
            db.execute('BEGIN')
            active = db.execute(f'''
                SELECT {columns} FROM handshakes WHERE starts_at IS NOT NULL
                ORDER BY starts_at DESC LIMIT 1
            ''').fetchone()
            pending = db.execute(f'''
                SELECT {columns} FROM handshakes WHERE starts_at IS NULL ORDER BY requested_at, id
            ''').fetchall()
            return jsonify(current=serialize(active), pending=[serialize(row) for row in pending],
                           server_now=now_ms())
        current = db.execute(f'SELECT {columns} FROM handshakes WHERE guest_id = ?',
                             (session['user_id'],)).fetchone()
        return jsonify(current=serialize(current), server_now=now_ms())

    @app.after_request
    def private_handshake(response):
        if request.path.startswith('/handshake'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.get('/')
    def home():
        return send_from_directory(ROOT, 'index.html')

    @app.get('/styles.css')
    @app.get('/language.js')
    @app.get('/handshake.css')
    @app.get('/handshake.js')
    def stylesheet_or_script():
        return send_from_directory(ROOT, request.path[1:])

    @app.get('/assets/<path:filename>')
    def assets(filename):
        return send_from_directory(ROOT / 'assets', filename)

    @app.get('/handshake')
    def handshake():
        signed_in = 'user_id' in session
        return render_template(
            'handshake.html', signed_in=signed_in, owner=is_owner(), oauth_ready=oauth_ready(),
            owner_configured=bool(app.config['OWNER_YANDEX_ID']), guest_name=session.get('guest_name'),
            account_id=session.get('user_id'), csrf_token=session.get('csrf_token'),
            login_error=request.args.get('login') == 'failed', animation_ms=ANIMATION_MS,
        )

    @app.get('/handshake/login')
    def login():
        if not oauth_ready() or 'user_id' in session:
            return redirect(url_for('handshake'))
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        session['oauth'] = {'state': state, 'verifier': verifier, 'expires': now_ms() + 600_000}
        params = urlencode({
            'response_type': 'code', 'client_id': app.config['YANDEX_CLIENT_ID'],
            'redirect_uri': app.config['YANDEX_REDIRECT_URI'], 'scope': 'login:info',
            'state': state, 'code_challenge': challenge.rstrip(b'=').decode(),
            'code_challenge_method': 'S256',
        })
        return redirect(f'https://oauth.yandex.ru/authorize?{params}')

    @app.get('/handshake/callback')
    def callback():
        oauth = session.pop('oauth', None)
        failure_url = url_for('handshake', login='failed')
        code = request.args.get('code')
        if (not oauth_ready() or not oauth or not code or oauth['expires'] < now_ms()
                or not same_token(oauth['state'], request.args.get('state'))):
            return redirect(failure_url)

        try:
            token_reply = requests.post(
                'https://oauth.yandex.ru/token',
                auth=(app.config['YANDEX_CLIENT_ID'], app.config['YANDEX_CLIENT_SECRET']),
                data={'grant_type': 'authorization_code', 'code': code,
                      'code_verifier': oauth['verifier']},
                timeout=8,
            )
            token_reply.raise_for_status()
            token = token_reply.json()['access_token']
            profile_reply = requests.get(
                'https://login.yandex.ru/info', params={'format': 'json'},
                headers={'Authorization': f'OAuth {token}'}, timeout=8,
            )
            profile_reply.raise_for_status()
            profile = profile_reply.json()
            account_id = profile['id']
            if not isinstance(account_id, str) or not account_id.isascii() or not account_id.isdecimal():
                return redirect(failure_url)
        except (requests.RequestException, KeyError, ValueError, TypeError):
            return redirect(failure_url)

        name = profile.get('first_name') or profile.get('display_name')
        name = name.strip()[:80] if isinstance(name, str) else ''
        session.clear()
        session.permanent = True
        session.update(user_id=account_id, guest_name=name, csrf_token=secrets.token_urlsafe(32))
        return redirect(url_for('handshake'))

    @app.post('/handshake/logout')
    def logout():
        if not same_token(session.get('csrf_token'), request.form.get('csrf_token')):
            return '', 403
        session.clear()
        return redirect(url_for('handshake'), 303)

    @app.before_request
    def check_api_session():
        if not request.path.startswith('/handshake/api/'):
            return
        if 'user_id' not in session:
            return jsonify(error='signInRequired'), 401
        if not app.config['OWNER_YANDEX_ID']:
            return jsonify(error='ownerUnavailable'), 503
        if request.method == 'POST' and not same_token(
            session.get('csrf_token'), request.headers.get('X-CSRF-Token')
        ):
            return jsonify(error='signInRequired'), 403

    @app.get('/handshake/api/status')
    def handshake_status():
        with closing(connect_db()) as db:
            return status(db)

    @app.post('/handshake/api/request')
    def request_handshake():
        if is_owner():
            return jsonify(error='actionUnavailable'), 403
        with closing(connect_db()) as db:
            requested_at = now_ms()
            with db:
                db.execute('''
                    INSERT INTO handshakes (id, guest_id, guest_name, requested_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(guest_id) DO UPDATE SET id = excluded.id,
                        guest_name = excluded.guest_name, requested_at = excluded.requested_at,
                        starts_at = NULL
                    WHERE handshakes.starts_at + ? <= excluded.requested_at
                ''', (uuid4().hex, session['user_id'], session['guest_name'], requested_at, ANIMATION_MS))
            return status(db)

    @app.post('/handshake/api/<request_id>/accept')
    def accept_handshake(request_id):
        if not is_owner():
            return jsonify(error='actionUnavailable'), 403
        with closing(connect_db()) as db:
            with db:
                db.execute('BEGIN IMMEDIATE')
                accepted_at = now_ms()
                db.execute('''
                    UPDATE handshakes SET starts_at = ?
                    WHERE id = ? AND starts_at IS NULL AND NOT EXISTS (
                        SELECT 1 FROM handshakes WHERE starts_at + ? > ?
                    )
                ''', (accepted_at + START_DELAY_MS, request_id, ANIMATION_MS, accepted_at))
            return status(db)

    return app
