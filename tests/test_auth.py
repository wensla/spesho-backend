import pytest
from app import db
from app.models.user import User


@pytest.fixture(autouse=True)
def clean_users(app):
    with app.app_context():
        yield
        db.session.query(User).filter(User.username.like('auth_test_%')).delete()
        db.session.commit()


def _create_user(app, username='auth_test_user', password='pass1234', role='salesperson'):
    with app.app_context():
        u = User(username=username, role=role, full_name='Auth Test')
        u.set_password(password)
        db.session.add(u)
        db.session.commit()


class TestLogin:
    def test_login_success(self, client, app):
        _create_user(app)
        resp = client.post('/api/auth/login', json={
            'username': 'auth_test_user',
            'password': 'pass1234',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'access_token' in data
        assert data['user']['username'] == 'auth_test_user'

    def test_login_wrong_password(self, client, app):
        _create_user(app)
        resp = client.post('/api/auth/login', json={
            'username': 'auth_test_user',
            'password': 'wrongpass',
        })
        assert resp.status_code == 401
        assert 'error' in resp.get_json()

    def test_login_missing_fields(self, client):
        resp = client.post('/api/auth/login', json={'username': 'someone'})
        assert resp.status_code == 400

    def test_login_inactive_user(self, client, app):
        with app.app_context():
            u = User(username='auth_test_inactive', role='salesperson', is_active=False)
            u.set_password('pass1234')
            db.session.add(u)
            db.session.commit()
        resp = client.post('/api/auth/login', json={
            'username': 'auth_test_inactive',
            'password': 'pass1234',
        })
        assert resp.status_code == 401

    def test_me_returns_current_user(self, client, app):
        _create_user(app, username='auth_test_me')
        login_resp = client.post('/api/auth/login', json={
            'username': 'auth_test_me',
            'password': 'pass1234',
        })
        token = login_resp.get_json()['access_token']
        resp = client.get('/api/auth/me',
                          headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 200
        assert resp.get_json()['user']['username'] == 'auth_test_me'

    def test_me_requires_auth(self, client):
        resp = client.get('/api/auth/me')
        assert resp.status_code == 401
